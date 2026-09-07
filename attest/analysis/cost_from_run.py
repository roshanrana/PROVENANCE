"""Turn a completed run directory into a cost-of-determinism report.

``attest.analysis.cost`` has always known how to compute the figure — bootstrap
confidence intervals over throughput and TTFT ratios, refusing to compare cells
whose conditions differ. What was missing was the join: nothing read a run
directory, split it into the invariance-off and invariance-on arms, and handed
the samples over. This is that join, and nothing more.

The split is on the **ledger's** recorded ``batch_invariant``, not on anything
inferred from the cell id. That matters because a stage-2 run is two engine
processes over one run-id, and a cell whose configuration the live engine did
not have is refused rather than run (``run._engine_disagrees_with``). So an arm
can legitimately be empty, and an empty arm must be reported as missing rather
than silently compared against itself.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from attest.analysis.cost import build_cost_report


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def load_arms(run_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split a run directory into (invariance-off, invariance-on) samples."""
    params: dict[str, dict[str, Any]] = {}
    ledger = run_dir / "cells.jsonl"
    if ledger.exists():
        for row in _load_jsonl(ledger):
            if row.get("params"):
                params[row["cell_id"]] = row["params"]

    arms: dict[bool, dict[str, Any]] = {
        False: {"latency_s": [], "tokens_per_s": [], "conditions": {}, "cells": []},
        True: {"latency_s": [], "tokens_per_s": [], "conditions": {}, "cells": []},
    }

    for cell_path in sorted(run_dir.glob("c*.jsonl")):
        if cell_path.stem == "cells":
            continue
        rows = _load_jsonl(cell_path)
        if not rows:
            continue
        cell_params = params.get(cell_path.stem, {})
        invariant = cell_params.get("batch_invariant")
        if invariant not in (True, False):
            continue  # unlabelled cell: not comparable, and guessing would be worse
        # A record without a latency predates the timing instrumentation. It is
        # skipped rather than defaulted, because a fabricated zero would drag
        # every interval computed from it toward a conclusion nobody measured.
        for row in rows:
            if "latency_s" in row and "tokens_per_s" in row:
                arms[invariant]["latency_s"].append(float(row["latency_s"]))
                arms[invariant]["tokens_per_s"].append(float(row["tokens_per_s"]))
        arms[invariant]["cells"].append(cell_path.stem)
        if not arms[invariant]["conditions"]:
            arms[invariant]["conditions"] = {
                k: v for k, v in cell_params.items() if k != "batch_invariant"
            }

    return arms[False], arms[True]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    off, on = load_arms(args.run_dir)

    if not off["latency_s"] or not on["latency_s"]:
        print("CANNOT BUILD A COST REPORT.")
        print(f"  invariance-off samples: {len(off['latency_s'])} (cells {off['cells']})")
        print(f"  invariance-on  samples: {len(on['latency_s'])} (cells {on['cells']})")
        print(
            "  A cost-of-determinism figure needs both arms measured under the\n"
            "  same conditions. Reporting one arm against itself, or against an\n"
            "  arm from a different run, would be a fabricated comparison."
        )
        return 2

    report = build_cost_report(
        throughput_off=off["tokens_per_s"],
        throughput_on=on["tokens_per_s"],
        ttft_off=off["latency_s"],
        ttft_on=on["latency_s"],
        conditions_off=off["conditions"],
        conditions_on=on["conditions"],
        rng_seed=args.seed,
    )

    print(report.headline())
    print()
    print(report.to_markdown())

    if args.out:
        args.out.write_text(
            json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
