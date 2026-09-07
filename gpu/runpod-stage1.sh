#!/usr/bin/env bash
#
# ATTEST stage 1, as a self-contained batch job — T-028 stage 1.
#
# Runs inside a RunPod pod. Nobody is watching it: an agent launches the pod,
# the pod runs this, and the agent reads the result out of the pod's log stream.
# So every step announces itself, every failure is loud, and the machine-readable
# result is framed by markers that survive interleaved engine output.
#
# The question stage 1 answers, and the only one:
#
#     does batched inference on THIS model and THIS card actually diverge?
#
# It is deliberately cheap and deliberately inconclusive about everything else.
# If divergence does not appear, that is the published result (NFR-17) and
# stage 2 is moot — which is exactly why the expensive run sits behind a human
# decision point rather than after an `&&`.
#
# Batch invariance is NOT enabled here. stage1_ladder() fixes batch_invariant to
# False for every cell, because the question is whether the *default* posture
# diverges. Turning it on would answer a different question at twice the cost.
#
#   REPO_SHA=<sha> ./gpu/runpod-stage1.sh
#
set -uo pipefail

MODEL="${MODEL:-Qwen/Qwen2.5-0.5B-Instruct}"
TRIALS="${TRIALS:-32}"
SEED="${SEED:-0}"
PORT="${PORT:-8000}"
READY_TIMEOUT_S="${READY_TIMEOUT_S:-900}"
RESULTS_ROOT="${RESULTS_ROOT:-/workspace/bench/results}"

say() { echo "[stage1] $*"; }
fail() { echo "[stage1] FATAL: $*" >&2; emit_and_exit 1; }

# ---------------------------------------------------------------- environment

say "=== ATTEST stage 1 ==="
say "started    : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
say "model      : $MODEL"
say "trials     : $TRIALS"

say "--- GPU ---"
nvidia-smi --query-gpu=name,memory.total,compute_cap,driver_version \
  --format=csv,noheader 2>&1 | sed 's/^/[stage1] /' || say "nvidia-smi unavailable"

# Compute capability >= 8.0 is a hard requirement for batch invariance
# (docs/design/00-upstream-findings.md §1.1). Checked before anything expensive:
# a run on a 7.5 card would produce numbers that cannot mean what they claim.
CC="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | head -1 | tr -d ' ')"
if [ -n "$CC" ]; then
  MAJOR="${CC%%.*}"
  if [ "${MAJOR:-0}" -lt 8 ]; then
    fail "compute capability $CC is below 8.0; batch invariance is unsupported here"
  fi
  say "compute capability $CC — OK"
else
  say "WARNING: could not read compute capability; continuing but the writeup must say so"
fi

# ---------------------------------------------------------------- the engine

say "--- launching vLLM (batch invariance OFF — stage 1 measures the default) ---"
export VLLM_BATCH_INVARIANT=0
# /server_info is registered only under this flag. Without it the readback
# degrades silently and the receipt records intent rather than reality (D-08).
export VLLM_SERVER_DEV_MODE=1

vllm serve "$MODEL" \
  --host 127.0.0.1 --port "$PORT" \
  --seed 0 \
  --no-enable-prefix-caching \
  --gpu-memory-utilization 0.90 \
  > /tmp/vllm.log 2>&1 &
ENGINE_PID=$!

cleanup() {
  say "--- tearing down the engine ---"
  kill "$ENGINE_PID" 2>/dev/null || true
  wait "$ENGINE_PID" 2>/dev/null || true
}
trap cleanup EXIT

say "waiting for readiness (up to ${READY_TIMEOUT_S}s)"
deadline=$(( $(date +%s) + READY_TIMEOUT_S ))
until curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; do
  if ! kill -0 "$ENGINE_PID" 2>/dev/null; then
    say "engine exited before becoming ready. Last 40 lines:"
    tail -40 /tmp/vllm.log | sed 's/^/[vllm] /'
    fail "engine did not start"
  fi
  if [ "$(date +%s)" -ge "$deadline" ]; then
    tail -40 /tmp/vllm.log | sed 's/^/[vllm] /'
    fail "engine not ready within ${READY_TIMEOUT_S}s"
  fi
  sleep 5
done
say "engine ready"

# The readback, captured verbatim before any measurement. If a field name has
# moved upstream this is where it becomes visible, rather than being inferred
# from a receipt that quietly recorded our own request back to us.
say "--- resolved configuration (D-08) ---"
mkdir -p "$RESULTS_ROOT"
curl -sf "http://127.0.0.1:$PORT/server_info?config_format=json" \
  > "$RESULTS_ROOT/server_info.json" 2>/dev/null \
  && say "captured $(wc -c < "$RESULTS_ROOT/server_info.json") bytes of /server_info" \
  || say "WARNING: /server_info unavailable — readback degraded, the writeup must say so"

# ---------------------------------------------------------------- the run

say "--- stage 1 ladder ---"
cd /workspace/provenance || fail "repo not found at /workspace/provenance"

set +e
uv run python -m attest.harness.run \
  --stage 1 \
  --engine-url "http://127.0.0.1:$PORT" \
  --seed "$SEED" \
  --trials "$TRIALS" \
  --results-root "$RESULTS_ROOT" \
  2>&1 | sed 's/^/[run] /'
RUN_RC="${PIPESTATUS[0]}"
set -e
say "run driver exited $RUN_RC"

# ---------------------------------------------------------------- delivery
#
# Two tiers, learned the hard way. The first run emitted the whole results tree
# as gzipped base64 — ~180 log lines — and the only channel out of a pod is its
# log stream, read back a bounded page at a time. Reassembling it cost more than
# the run. So the summary is always printed and the payload is opt-in.

emit_and_exit() {
  local rc="${1:-0}"

  say "--- summary ---"
  # The newest run directory: the driver names them with a sortable run-id.
  RUN_DIR="$(ls -1dt "$RESULTS_ROOT"/*/ 2>/dev/null | head -1)"
  if [ -n "${RUN_DIR:-}" ]; then
    uv run python gpu/summarise_stage1.py --run-dir "${RUN_DIR%/}" 2>&1 || \
      say "WARNING: summariser failed; the raw JSONL is still on the pod"
  else
    say "WARNING: no run directory under $RESULTS_ROOT — nothing to summarise"
  fi

  if [ "${EMIT_PAYLOAD:-0}" = "1" ]; then
    say "--- payload (EMIT_PAYLOAD=1) ---"
    local bundle="/tmp/stage1-payload.tgz"
    tar czf "$bundle" -C "$(dirname "$RESULTS_ROOT")" "$(basename "$RESULTS_ROOT")" 2>/dev/null \
      || tar czf "$bundle" --files-from /dev/null
    echo "-----BEGIN PROVENANCE STAGE1 PAYLOAD-----"
    base64 -w 120 "$bundle"
    echo "-----END PROVENANCE STAGE1 PAYLOAD-----"
    say "payload bytes: $(wc -c < "$bundle")"
  else
    say "payload suppressed (set EMIT_PAYLOAD=1 to dump the full results tree)"
  fi

  say "exit rc=$rc"
  say "=== ATTEST stage 1 complete ==="
  exit "$rc"
}

emit_and_exit "$RUN_RC"
