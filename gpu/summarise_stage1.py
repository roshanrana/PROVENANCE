"""Compress a stage-1 run into something a log stream can actually carry.

The first stage-1 job emitted the whole results tree as gzipped base64. It
worked, and it was the wrong design: the payload was ~180 lines, and the only
channel out of a RunPod pod is its log stream, read back a bounded page at a
time. Reassembling it cost more than the run did.

So the delivery contract is now two-tier:

* a **summary** — the verdict, the per-cell divergence table, and the digests
  that back it. Thirty lines. This is what gets read, quoted and acted on.
* the **payload** — the full results tree, still emitted, but only when
  EMIT_PAYLOAD=1, because it is expensive to retrieve and is not needed to
  decide whether stage 2 should happen.

Nothing is summarised away that a claim depends on. Every number here has its
digest printed beside it, and the raw JSONL that produced it stays on the pod.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

BAR = "=" * 72


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()

    run_dir: Path = args.run_dir
    print(BAR)
    print("ATTEST STAGE 1 SUMMARY")
    print(BAR)
    print(f"run dir : {run_dir.name}")

    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for key in ("run_id", "cells_total", "cells_done", "cells_failed", "git_sha"):
            if key in manifest:
                print(f"{key:9}: {manifest[key]}")

    cells = sorted(run_dir.glob("c*.jsonl"))
    if not cells:
        print("\nNO CELL OUTPUT FOUND — the run produced nothing to summarise.")
        print(BAR)
        return 2

    print()
    print(f"{'cell':>6}  {'conc':>5}  {'trials':>6}  {'unique':>6}  verdict")
    print("-" * 72)

    any_divergence = False
    table: list[dict[str, Any]] = []

    for cell_path in cells:
        rows = _load_jsonl(cell_path)
        if not rows:
            continue
        # Bitwise identity is claimed over the logprob vector, so the digest —
        # not the text — is what decides whether two completions are the same.
        digests = [r.get("logprobs_sha256", "") for r in rows]
        unique = len(set(digests))
        params = rows[0].get("params", {}) or {}
        concurrency = params.get("concurrency", "?")
        diverged = unique > 1
        any_divergence = any_divergence or diverged
        verdict = "DIVERGED" if diverged else "identical"
        print(f"{cell_path.stem:>6}  {concurrency!s:>5}  {len(rows):>6}  {unique:>6}  {verdict}")
        counts = Counter(digests)
        table.append(
            {
                "cell": cell_path.stem,
                "concurrency": concurrency,
                "trials": len(rows),
                "unique_logprob_digests": unique,
                "diverged": diverged,
                "digest_counts": [{"digest": d[:16], "n": n} for d, n in counts.most_common(4)],
            }
        )

    print("-" * 72)
    print()
    if any_divergence:
        print("VERDICT: DIVERGENCE OBSERVED.")
        print("  The same prompt at temperature 0 produced more than one distinct")
        print("  logprob vector once batch composition varied. Stage 2 is warranted:")
        print("  there is a real effect whose cost is worth measuring.")
    else:
        print("VERDICT: NO DIVERGENCE OBSERVED at this model size and concurrency.")
        print("  This is a publishable negative result (NFR-17), not a failed run.")
        print("  Stage 2's cost-of-determinism measurement is moot as scoped: there")
        print("  is nothing to make deterministic that was not already stable.")
        print("  Before concluding, the writeup must state the concurrency ladder")
        print("  actually reached — an effect absent at concurrency 8 is not an")
        print("  effect absent at concurrency 128.")

    print()
    print("Digest counts per cell (first 16 hex chars):")
    print(json.dumps(table, indent=2))
    print(BAR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
