"""Divergence analysis — raw run output to the tables FR-A-01/03/04 publish.

Two rules govern everything here, and both exist because the failure mode of this
project is a plausible wrong number rather than an obvious crash:

* **Comparison is bitwise.** FR-A-03 claims bitwise identity. Comparing rendered
  text, or logprobs within a tolerance, would let a genuinely divergent run be
  reported as reproducible.
* **An incomplete matrix produces no headline number.** If cells are missing or
  failed, the analysis names them and refuses (exit 8, LLD §5). A mean over
  whichever cells happened to survive is survivor bias with a confidence interval
  drawn around it.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from attest.harness.ledger import CellState, Ledger


class IncompleteMatrix(RuntimeError):
    """Refusal to summarise a run that did not finish. Maps to exit code 8."""


@dataclass(frozen=True)
class Observation:
    """One trial: the bitwise identity of what the engine returned."""

    cell_id: str
    trial: int
    token_ids: tuple[int, ...]
    logprobs_sha256: str

    @property
    def fingerprint(self) -> tuple[tuple[int, ...], str]:
        """Tokens *and* logprobs. Two completions can render the same text from
        different logprobs; that is still divergence, and it is the earlier
        symptom — the bits move before the words do."""
        return (self.token_ids, self.logprobs_sha256)


@dataclass(frozen=True)
class CellSummary:
    cell_id: str
    params: Mapping[str, Any]
    trials: int
    unique_completions: int
    unique_token_sequences: int
    bitwise_identical: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "model": self.params.get("model"),
            "concurrency": self.params.get("concurrency"),
            "max_tokens": self.params.get("max_tokens"),
            "heterogeneity": self.params.get("length_heterogeneity"),
            "batch_invariant": self.params.get("batch_invariant"),
            "trials": self.trials,
            "unique_completions": self.unique_completions,
            "unique_token_sequences": self.unique_token_sequences,
            "bitwise_identical": self.bitwise_identical,
        }


@dataclass(frozen=True)
class DivergenceReport:
    run_id: str
    cells: Sequence[CellSummary]

    @property
    def invariance_off(self) -> list[CellSummary]:
        return [c for c in self.cells if not c.params.get("batch_invariant")]

    @property
    def invariance_on(self) -> list[CellSummary]:
        return [c for c in self.cells if c.params.get("batch_invariant")]

    def divergence_observed(self) -> bool:
        """True if any invariance-off cell produced more than one completion.

        If this is False the honest result is 'no divergence observed at these
        configurations', published as such (NFR-17) — not quietly dropped.
        """
        return any(c.unique_completions > 1 for c in self.invariance_off)

    def reproducibility_holds(self) -> bool:
        """True if every invariance-on cell is bitwise identical across trials.

        Vacuously true when no invariance-on cells were run, so callers must check
        that they exist — `summary_lines` says so explicitly rather than letting an
        empty sweep read as a proof.
        """
        return all(c.bitwise_identical for c in self.invariance_on)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "cells": [c.to_dict() for c in self.cells],
            "divergence_observed": self.divergence_observed(),
            "reproducibility_holds": self.reproducibility_holds(),
            "n_cells_invariance_off": len(self.invariance_off),
            "n_cells_invariance_on": len(self.invariance_on),
        }

    def summary_lines(self) -> list[str]:
        lines = [f"run {self.run_id}: {len(self.cells)} cells"]
        if not self.invariance_off:
            lines.append("no invariance-off cells — divergence was not tested")
        elif self.divergence_observed():
            worst = max(self.invariance_off, key=lambda c: c.unique_completions)
            lines.append(
                f"divergence observed: up to {worst.unique_completions} unique "
                f"completions in {worst.cell_id} "
                f"(concurrency={worst.params.get('concurrency')}, "
                f"model={worst.params.get('model')})"
            )
        else:
            lines.append(
                "NO divergence observed at any tested configuration — "
                "this is the result, and it is published as such (NFR-17)"
            )

        if not self.invariance_on:
            lines.append("no invariance-on cells — reproducibility was not tested")
        elif self.reproducibility_holds():
            lines.append(
                f"reproducibility holds: all {len(self.invariance_on)} invariance-on "
                "cells bitwise identical across trials"
            )
        else:
            broken = [c.cell_id for c in self.invariance_on if not c.bitwise_identical]
            lines.append(f"REPRODUCIBILITY FAILED in: {', '.join(broken)}")
        return lines


def read_observations(path: Path) -> list[Observation]:
    """Read one cell's raw JSONL. Malformed lines are an error, not a shrug."""
    observations: list[Observation] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            observations.append(
                Observation(
                    cell_id=record["cell_id"],
                    trial=int(record.get("trial", lineno - 1)),
                    token_ids=tuple(int(t) for t in record["token_ids"]),
                    logprobs_sha256=record["logprobs_sha256"],
                )
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{path}:{lineno}: unusable observation: {exc}") from exc
    return observations


def summarise_cell(
    cell_id: str, params: Mapping[str, Any], observations: Iterable[Observation]
) -> CellSummary:
    observed = list(observations)
    if not observed:
        raise ValueError(f"{cell_id}: no observations")

    fingerprints = {o.fingerprint for o in observed}
    token_sequences = {o.token_ids for o in observed}
    return CellSummary(
        cell_id=cell_id,
        params=dict(params),
        trials=len(observed),
        unique_completions=len(fingerprints),
        unique_token_sequences=len(token_sequences),
        bitwise_identical=len(fingerprints) == 1,
    )


def analyse_run(run_dir: Path) -> DivergenceReport:
    """Summarise a completed run.

    Refuses an incomplete or partially failed matrix by design (LLD §5, exit 8).
    """
    ledger = Ledger.in_dir(run_dir)
    states = ledger.states()
    if not states:
        raise IncompleteMatrix(f"{run_dir}: ledger is empty")

    unfinished = [
        c.cell_id for c in states.values() if c.state in (CellState.PENDING, CellState.RUNNING)
    ]
    failed = [c.cell_id for c in states.values() if c.state is CellState.FAILED]
    if unfinished or failed:
        parts = []
        if unfinished:
            parts.append(f"{len(unfinished)} unfinished ({', '.join(sorted(unfinished)[:5])})")
        if failed:
            parts.append(f"{len(failed)} failed ({', '.join(sorted(failed)[:5])})")
        raise IncompleteMatrix(
            f"INCOMPLETE MATRIX: {'; '.join(parts)} — refusing to emit a headline "
            "number over a partial run"
        )

    by_cell: dict[str, list[Observation]] = defaultdict(list)
    summaries: list[CellSummary] = []
    for cell_id, record in sorted(states.items()):
        raw_path = run_dir / (record.output_path or f"{cell_id}.jsonl")
        if not raw_path.exists():
            raise IncompleteMatrix(f"{cell_id}: marked done but {raw_path} is missing")
        by_cell[cell_id] = read_observations(raw_path)
        summaries.append(summarise_cell(cell_id, record.params, by_cell[cell_id]))

    return DivergenceReport(run_id=run_dir.name, cells=summaries)


def to_markdown_table(report: DivergenceReport) -> str:
    """The table FR-A-01 publishes. Regenerated by script, never hand-edited."""
    header = (
        "| cell | model | concurrency | max_tokens | heterogeneity | invariant "
        "| trials | unique completions |\n"
        "|---|---|---|---|---|---|---|---|"
    )
    rows = [
        f"| {c.cell_id} | {c.params.get('model', '?')} | {c.params.get('concurrency', '?')} "
        f"| {c.params.get('max_tokens', '?')} | {c.params.get('length_heterogeneity', '?')} "
        f"| {'yes' if c.params.get('batch_invariant') else 'no'} | {c.trials} "
        f"| {c.unique_completions} |"
        for c in report.cells
    ]
    return "\n".join([header, *rows])
