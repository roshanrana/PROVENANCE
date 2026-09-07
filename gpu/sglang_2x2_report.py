"""Turn the four A-03 cells into the decomposition ADR-009 exists for.

The point of the 2x2 is not four numbers, it is two *differences*:

    C - D   what the radix cache is worth while determinism is on
    D - B   what determinism costs on its own, cache held off

On vLLM only the sum is observable, because determinism and caching cannot be on
together. Reporting the sum as "the cost of determinism" is the confound this
whole amendment exists to remove, so this script refuses to print a
decomposition when a cell is missing rather than quietly computing it from three.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

CELLS = {
    "A-nondet-cache": ("nondeterministic", "cache on"),
    "B-nondet-nocache": ("nondeterministic", "cache off"),
    "C-det-cache": ("deterministic", "cache on"),
    "D-det-nocache": ("deterministic", "cache off"),
}


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dir", type=Path, required=True)
    args = p.parse_args()

    cells: dict[str, dict[str, Any]] = {}
    for label in CELLS:
        path = args.dir / f"{label}.json"
        if path.exists():
            cells[label] = json.loads(path.read_text(encoding="utf-8"))

    print(f"{'cell':<18} {'determinism':<17} {'cache':<10} {'n':>4} {'unique':>7} {'tok/s':>9}")
    print("-" * 72)
    for label, (det, cache) in CELLS.items():
        cell = cells.get(label)
        if cell is None:
            print(f"{label:<18} {det:<17} {cache:<10} {'—':>4} {'—':>7} {'MISSING':>9}")
            continue
        throughput = _mean([r["tokens_per_s"] for r in cell["records"]])
        print(
            f"{label:<18} {det:<17} {cache:<10} {cell['trials']:>4} "
            f"{cell['unique_logprob_digests']:>7} {throughput:>9.1f}"
        )
    print()

    missing = [label for label in CELLS if label not in cells]
    if missing:
        print(f"CANNOT DECOMPOSE — missing cells: {missing}")
        print(
            "  The 2x2 is worth having only for the two differences it supports.\n"
            "  Computing them from three cells would be inventing the fourth."
        )
        return 2

    def tput(label: str) -> float:
        return _mean([r["tokens_per_s"] for r in cells[label]["records"]])

    def lat(label: str) -> float:
        return _median([r["latency_s"] for r in cells[label]["records"]])

    cache_worth = tput("C-det-cache") / tput("D-det-nocache")
    determinism_cost = tput("D-det-nocache") / tput("B-nondet-nocache")
    naive_sum = tput("C-det-cache") / tput("A-nondet-cache")

    print("DECOMPOSITION (throughput ratios, mean tokens/s)")
    print(f"  cache worth under determinism   C/D = {cache_worth:.3f}x")
    print(f"  determinism cost, cache off     D/B = {determinism_cost:.3f}x")
    print(f"  both together                   C/A = {naive_sum:.3f}x")
    print()
    print("MEDIAN LATENCY (s)")
    for label in CELLS:
        print(f"  {label:<18} {lat(label):.4f}")
    print()
    print("DIVERGENCE")
    for label in CELLS:
        print(
            f"  {label:<18} {cells[label]['unique_logprob_digests']:>3} distinct "
            f"of {cells[label]['trials']}"
        )
    print()
    print(
        "The vLLM cost figure can only ever be the C/A column, because vLLM\n"
        "cannot hold determinism and prefix caching at once. Whether that is a\n"
        "fair proxy for D/B is exactly what these numbers answer."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
