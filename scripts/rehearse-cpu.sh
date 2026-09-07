#!/usr/bin/env bash
#
# CPU dress rehearsal — run the ATTEST harness against a REAL vLLM.
#
# Why this exists
# ---------------
# Every ATTEST test so far runs against tests/support/stub_engine.py — a server
# this project wrote, which therefore agrees with this project by construction.
# The stub cannot disagree, and a fixture that cannot disagree cannot find a bug.
#
# This runs the same harness against real vLLM on CPU. It measures nothing:
# batch invariance needs an NVIDIA GPU of compute capability >= 8.0 and is
# unsupported on CPU (docs/design/00-upstream-findings.md §1.1), so the flag is
# not even set here. What it proves is that the *plumbing* is right — argv,
# readiness, config readback, wire format — while that is still free to
# discover. The alternative is discovering it on rented hardware with the clock
# running.
#
# It has already earned its keep once: writing it surfaced that vLLM populates
# CompletionResponseChoice.token_ids only when the request sets
# return_token_ids, which the harness never did. The receipt's subject digest is
# computed over token ids, so every receipt from a real engine would have had
# nothing to bind.
#
# Requirements: Docker (Desktop with the WSL2 backend is fine), ~10 GB disk for
# the image, ~6 GB RAM for the model. No GPU. Nothing is installed on the host.
#
#   ./scripts/rehearse-cpu.sh              # full rehearsal
#   KEEP_ENGINE=1 ./scripts/rehearse-cpu.sh  # leave vLLM up for poking
#
set -euo pipefail

MODEL="${MODEL:-Qwen/Qwen2.5-0.5B-Instruct}"
PORT="${PORT:-8000}"
IMAGE="${IMAGE:-public.ecr.aws/q9t5s3a7/vllm-cpu-release-repo:latest}"
CONTAINER="${CONTAINER:-provenance-vllm-cpu}"
READY_TIMEOUT_S="${READY_TIMEOUT_S:-900}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
OUT_DIR="${OUT_DIR:-$REPO_ROOT/bench/results/rehearsal-cpu}"

mkdir -p "$OUT_DIR"
exec > >(tee "$OUT_DIR/rehearsal.log") 2>&1

echo "=== ATTEST CPU rehearsal ==="
echo "model     : $MODEL"
echo "image     : $IMAGE"
echo "started   : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "NOTE      : determinism is NOT enabled and NOT measured here. CPU cannot."
echo

if ! command -v docker >/dev/null 2>&1; then
  echo "MISSING: docker is not on PATH." >&2
  exit 3
fi

cleanup() {
  if [ "${KEEP_ENGINE:-0}" = "1" ]; then
    echo
    echo "KEEP_ENGINE=1 — leaving '$CONTAINER' up on port $PORT."
    echo "Stop it with: docker rm -f $CONTAINER"
    return
  fi
  echo
  echo "--- tearing down ---"
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker rm -f "$CONTAINER" >/dev/null 2>&1 || true

echo "--- starting vLLM (CPU) ---"
echo "First run pulls a large image and downloads weights; allow 10-20 minutes."
# --shm-size: vLLM's default IPC needs more than Docker's 64 MB.
# VLLM_CPU_KVCACHE_SPACE is in GiB and has no useful default on CPU.
docker run -d --name "$CONTAINER" \
  -p "$PORT:8000" \
  --shm-size=4g \
  -e VLLM_CPU_KVCACHE_SPACE="${VLLM_CPU_KVCACHE_SPACE:-4}" \
  -e HF_TOKEN="${HF_TOKEN:-}" \
  -v "${HF_CACHE:-$HOME/.cache/huggingface}:/root/.cache/huggingface" \
  "$IMAGE" \
  --model "$MODEL" \
  --host 0.0.0.0 \
  --port 8000 \
  --seed 0 \
  --no-enable-prefix-caching \
  --dtype bfloat16 \
  >/dev/null

echo "--- waiting for readiness (up to ${READY_TIMEOUT_S}s) ---"
deadline=$(( $(date +%s) + READY_TIMEOUT_S ))
until curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; do
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "ENGINE DID NOT BECOME READY. Last 40 log lines:" >&2
    docker logs --tail 40 "$CONTAINER" >&2 || true
    exit 4
  fi
  if [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" != "true" ]; then
    echo "ENGINE EXITED. Last 40 log lines:" >&2
    docker logs --tail 40 "$CONTAINER" >&2 || true
    exit 4
  fi
  sleep 5
done
echo "ready."
echo

echo "--- capturing what the engine actually exposes ---"
# Kept verbatim because read_resolved_state() guesses at these field names, and
# a guess that is wrong fails SILENTLY: _observed_* returns None, the receipt
# records what we asked for instead of what was resolved, and D-08 is violated
# by a receipt that looks perfectly well-formed.
for endpoint in /version /v1/server_info /v1/models; do
  name="$(echo "$endpoint" | tr '/' '_')"
  echo "GET $endpoint"
  curl -sf "http://127.0.0.1:$PORT$endpoint" \
    | tee "$OUT_DIR/raw${name}.json" | head -c 600 || echo "  (unavailable)"
  echo
done
echo

echo "--- running the harness against it ---"
cd "$REPO_ROOT"
uv run python scripts/_rehearse_cpu_check.py \
  --base-url "http://127.0.0.1:$PORT" \
  --model "$MODEL" \
  --out "$OUT_DIR/findings.json"

echo
echo "=== rehearsal complete ==="
echo "raw responses and findings: $OUT_DIR"
