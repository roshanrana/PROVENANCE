"""Measure one cell of the A-03 2x2 against a live SGLang engine.

Deliberately not routed through ``attest.harness.run``. That driver's matrix is
built around ``batch_invariant`` as the only varying axis; A-03 varies a second
one (the radix cache), and bending the frozen ``CellParams`` contract to fit an
amendment would be a plan change, not a convenience.

What it does share with the driver is the part that matters: identical requests,
temperature 0, a fixed seed, per-request wall clock from a monotonic clock, and
the digest over the logprob vector as the definition of "same output".
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx

from attest.harness.engine import logprobs_digest

PROMPT = "Summarise the counterparty exposure in one sentence."


def _one(client: httpx.Client, base_url: str, model: str, max_tokens: int) -> dict[str, Any]:
    body = {
        "model": model,
        "prompt": PROMPT,
        "temperature": 0.0,
        "top_p": 1.0,
        "max_tokens": max_tokens,
        "logprobs": 1,
    }
    started = time.perf_counter()
    response = client.post(f"{base_url}/v1/completions", json=body, timeout=120.0)
    latency_s = time.perf_counter() - started
    response.raise_for_status()
    choice = response.json()["choices"][0]

    raw = (choice.get("logprobs") or {}).get("token_logprobs")
    if raw is None:
        raise RuntimeError("engine returned no token_logprobs; nothing to digest")
    holes = [i for i, x in enumerate(raw) if x is None]
    if holes:
        # Same refusal as the vLLM client: coercing a null to 0.0 would fabricate
        # a value and make two genuinely different runs digest identically.
        raise RuntimeError(f"null logprobs at {holes[:8]} of {len(raw)}")

    logprobs = [float(x) for x in raw]
    return {
        "latency_s": latency_s,
        "output_tokens": len(logprobs),
        "tokens_per_s": (len(logprobs) / latency_s) if latency_s > 0 else 0.0,
        "logprobs_sha256": logprobs_digest(logprobs),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--label", required=True)
    p.add_argument("--deterministic", required=True)
    p.add_argument("--caching", required=True)
    p.add_argument("--trials", type=int, default=128)
    p.add_argument("--max-tokens", type=int, default=128)
    p.add_argument("--concurrency", type=int, default=16)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    with (
        httpx.Client() as client,
        ThreadPoolExecutor(max_workers=args.concurrency) as pool,
    ):
        futures = [
            pool.submit(_one, client, args.base_url, args.model, args.max_tokens)
            for _ in range(args.trials)
        ]
        records = [f.result() for f in futures]

    digests = [r["logprobs_sha256"] for r in records]
    summary = {
        "label": args.label,
        "deterministic": args.deterministic == "1",
        "caching": args.caching == "1",
        "trials": len(records),
        "unique_logprob_digests": len(set(digests)),
        "records": records,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(
        f"{args.label}: n={len(records)} unique={len(set(digests))} "
        f"median_latency={sorted(r['latency_s'] for r in records)[len(records) // 2]:.4f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
