#!/usr/bin/env bash
#
# A-03 — the caching × determinism 2×2, on SGLang. ADR-009.
#
# This is the arm the H100 was chosen for, and the reason SGLang is in the
# project at all.
#
# vLLM cannot run batch-invariant kernels with prefix caching on: the two are not
# integrated upstream, so D-06 pins caching off for ATTEST's primary claim. That
# makes the vLLM cost figure a *sum* — determinism plus the loss of the cache —
# with no way to separate the halves. Every number in
# bench/results/cost-h100-2026-09-07.md carries that confound.
#
# SGLang runs deterministically WITH its radix cache on, on FA3 or Triton. So:
#
#                      caching on        caching off
#   nondeterministic       A                  B
#   deterministic          C                  D
#
#   C − D  isolates what the cache is worth under determinism
#   D − B  isolates what determinism costs on its own
#
# On vLLM only A − D is observable, and it gets reported as "the cost of
# determinism" when it is not.
#
# FA3 is Hopper-only, which is why this runs on an H100 rather than the A40 that
# was fine for everything else. Triton would work on Ampere and is the fallback
# if FA3 misbehaves — the harness refuses FlashInfer here, because FlashInfer
# cannot do deterministic inference with the radix cache on and that is the one
# cell the whole exercise exists to produce.
#
set -uo pipefail

MODEL="${MODEL:-Qwen/Qwen2.5-0.5B-Instruct}"
BACKEND="${BACKEND:-fa3}"
TRIALS="${TRIALS:-128}"
MAXTOK="${MAXTOK:-128}"
CONCURRENCY="${CONCURRENCY:-16}"
PORT="${PORT:-30000}"
READY_TIMEOUT_S="${READY_TIMEOUT_S:-900}"
OUT="${OUT:-/workspace/bench/results/sglang-2x2}"

say() { echo "[2x2] $*"; }

mkdir -p "$OUT"
say "=== A-03: caching × determinism on SGLang ==="
say "model    : $MODEL"
say "backend  : $BACKEND"
say "trials   : $TRIALS at concurrency $CONCURRENCY, $MAXTOK max tokens"
nvidia-smi --query-gpu=name,compute_cap --format=csv,noheader | sed 's/^/[2x2] /'

run_cell() {
  local deterministic="$1" caching="$2" label="$3"
  say "--- cell $label: deterministic=$deterministic caching=$caching ---"

  local args=(--model-path "$MODEL" --host 127.0.0.1 --port "$PORT"
              --random-seed 0 --attention-backend "$BACKEND")
  [ "$deterministic" = "1" ] && args+=(--enable-deterministic-inference)
  # Inverted sense: there is no --enable-radix-cache to pair with it.
  [ "$caching" = "0" ] && args+=(--disable-radix-cache)

  python3 -m sglang.launch_server "${args[@]}" > "/tmp/sglang-$label.log" 2>&1 &
  local pid=$!

  local deadline=$(( $(date +%s) + READY_TIMEOUT_S ))
  until curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; do
    if ! kill -0 "$pid" 2>/dev/null; then
      say "ENGINE DIED for $label. Last 30 lines:"
      tail -30 "/tmp/sglang-$label.log" | sed 's/^/[sglang] /'
      return 1
    fi
    if [ "$(date +%s)" -ge "$deadline" ]; then
      say "ENGINE TIMEOUT for $label"
      tail -30 "/tmp/sglang-$label.log" | sed 's/^/[sglang] /'
      kill "$pid" 2>/dev/null; return 1
    fi
    sleep 5
  done
  say "engine ready"

  # Read back what it resolved, before measuring anything (D-08). If the engine
  # silently lost the radix cache, the cell measured is not the cell requested,
  # and the whole 2×2 turns into four copies of the same experiment.
  curl -sf "http://127.0.0.1:$PORT/get_server_info" -o "$OUT/server_info-$label.json" \
    && say "captured $(wc -c < "$OUT/server_info-$label.json") bytes of /get_server_info" \
    || say "WARNING: /get_server_info unavailable — readback degraded, say so in the writeup"

  uv run python gpu/sglang_cell.py \
    --base-url "http://127.0.0.1:$PORT" \
    --model "$MODEL" \
    --label "$label" \
    --deterministic "$deterministic" \
    --caching "$caching" \
    --trials "$TRIALS" \
    --max-tokens "$MAXTOK" \
    --concurrency "$CONCURRENCY" \
    --out "$OUT/$label.json" 2>&1 | sed 's/^/[cell] /'

  kill "$pid" 2>/dev/null
  wait "$pid" 2>/dev/null
  sleep 10
  say "engine stopped"
}

# Order matters only for legibility; each cell is an independent engine process.
run_cell 0 1 "A-nondet-cache"   || say "cell A failed"
run_cell 0 0 "B-nondet-nocache" || say "cell B failed"
run_cell 1 1 "C-det-cache"      || say "cell C failed"
run_cell 1 0 "D-det-nocache"    || say "cell D failed"

echo "===2X2_START==="
uv run python gpu/sglang_2x2_report.py --dir "$OUT" 2>&1
echo "===2X2_END==="
