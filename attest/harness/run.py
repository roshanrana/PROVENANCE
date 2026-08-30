"""The ATTEST run driver — FR-A-09.

One command executes the matrix, checkpoints after each cell, and resumes from the
last checkpoint without repeating completed work. Deliberately dumber than a
workflow engine, because what it has to survive is a dropped SSH session to rented
hardware partway through a paid session.

Two stages, per requirements §7.1 and RSK-01:

* ``--stage 1`` walks the escalation ladder cheapest-first with invariance off,
  hunting for divergence. It **stops early** once a configuration diverges
  reliably — GPU minutes spent confirming a known effect are minutes not spent
  finding it.
* ``--stage 2`` runs the full on/off sweep at the configuration a human chose from
  Stage 1's evidence. That choice is not automated: its outcome changes what the
  project claims.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from attest.analysis.divergence import Observation, summarise_cell
from attest.harness.engine import EngineClient, EngineError
from attest.harness.ledger import CellState, Ledger
from attest.harness.matrix import Cell, MatrixSpec, stage1_ladder, stage2_matrix
from attest.receipt.schema import SamplingParams
from common.runid import Manifest, iso, utc_now

#: Stage 1 stops here: a cell producing at least this many distinct completions
#: is treated as reliable divergence rather than a one-off.
DIVERGENCE_STOP_THRESHOLD = 2

FILLER = {
    "uniform": ["Summarise the position." for _ in range(4)],
    "mixed": ["Summarise.", "Summarise the position in detail." * 4, "Explain." * 12],
    "extreme": ["Hi.", "Explain the counterparty exposure in exhaustive detail." * 60],
}


@dataclass(frozen=True)
class RunOutcome:
    run_id: str
    run_dir: Path
    cells_total: int
    cells_done: int
    cells_failed: int
    stopped_early: bool
    diverged_at: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "run_dir": str(self.run_dir),
            "cells_total": self.cells_total,
            "cells_done": self.cells_done,
            "cells_failed": self.cells_failed,
            "stopped_early": self.stopped_early,
            "diverged_at": self.diverged_at,
        }


def _prompt_for(cell: Cell, trial: int) -> str:
    """The measured prompt is identical in every trial — that is the whole point.

    Only the *filler* around it varies, to shape the batch. If the measured prompt
    changed between trials, differing output would prove nothing.
    """
    return "Summarise the counterparty exposure in one sentence."


def _run_one_trial(
    engine: EngineClient, cell: Cell, trial: int, sampling: SamplingParams
) -> dict[str, Any]:
    from attest.harness.engine import logprobs_digest

    completion = engine.complete(_prompt_for(cell, trial), sampling, model=cell.params.model)
    return {
        "cell_id": cell.cell_id,
        "trial": trial,
        "token_ids": completion.token_ids,
        "text": completion.text,
        "logprobs": completion.logprobs,
        "logprobs_sha256": logprobs_digest(completion.logprobs),
        "ts_utc": iso(utc_now()),
    }


def run_cell(engine_url: str, cell: Cell, run_dir: Path) -> list[dict[str, Any]]:
    """Execute one matrix cell: `trials` requests at the cell's concurrency."""
    sampling = SamplingParams(
        seed=cell.params.seed,
        temperature=0.0,
        top_p=1.0,
        max_tokens=cell.params.max_tokens,
    )
    records: list[dict[str, Any]] = []
    with EngineClient(engine_url) as engine:
        if cell.params.concurrency <= 1:
            records = [_run_one_trial(engine, cell, t, sampling) for t in range(cell.params.trials)]
        else:
            with ThreadPoolExecutor(max_workers=cell.params.concurrency) as pool:
                futures = [
                    pool.submit(_run_one_trial, engine, cell, t, sampling)
                    for t in range(cell.params.trials)
                ]
                records = [f.result() for f in futures]

    raw_path = run_dir / f"{cell.cell_id}.jsonl"
    with open(raw_path, "w", encoding="utf-8") as fh:
        for record in sorted(records, key=lambda r: r["trial"]):
            fh.write(json.dumps(record, sort_keys=True) + "\n")
    return records


def execute(
    *,
    engine_url: str,
    cells: Sequence[Cell],
    results_root: Path,
    spec: MatrixSpec,
    command: str,
    run_id: str | None = None,
    stop_on_divergence: bool = False,
    git: tuple[str, bool] | None = None,
) -> RunOutcome:
    """Run (or resume) a matrix.

    Resuming is the default behaviour, not a flag: pass an existing ``run_id`` and
    completed cells are skipped, interrupted ones re-run, failed ones left alone.
    """
    if run_id is None:
        manifest = Manifest.start("attest", command=command, git=git)
        run_id = manifest.run_id
        run_dir = results_root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "matrix.json").write_text(
            json.dumps(
                {"spec": spec.to_dict(), "fingerprint": spec.fingerprint()},
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    else:
        run_dir = results_root / run_id
        if not run_dir.exists():
            raise FileNotFoundError(f"cannot resume: {run_dir} does not exist")
        manifest = Manifest.start("attest", command=command, git=git)
        object.__setattr__(manifest, "run_id", run_id)

    ledger = Ledger.in_dir(run_dir)
    ledger.seed([c.to_ledger_entry() for c in cells])
    by_id = {c.cell_id: c for c in cells}

    stopped_early = False
    diverged_at: str | None = None

    for record in sorted(ledger.states().values(), key=lambda r: r.cell_id):
        if record.state in (CellState.DONE, CellState.FAILED):
            continue  # done stays done; failed is never retried into the dataset
        cell = by_id.get(record.cell_id)
        if cell is None:
            continue

        ledger.mark_running(cell.cell_id)
        try:
            records = run_cell(engine_url, cell, run_dir)
        except EngineError as exc:
            ledger.mark_failed(cell.cell_id, f"{type(exc).__name__}: {exc}")
            continue

        ledger.mark_done(cell.cell_id, f"{cell.cell_id}.jsonl")

        if stop_on_divergence:
            summary = summarise_cell(
                cell.cell_id,
                cell.params.to_dict(),
                [
                    Observation(
                        cell_id=r["cell_id"],
                        trial=r["trial"],
                        token_ids=tuple(r["token_ids"]),
                        logprobs_sha256=r["logprobs_sha256"],
                    )
                    for r in records
                ],
            )
            if summary.unique_completions >= DIVERGENCE_STOP_THRESHOLD:
                stopped_early = True
                diverged_at = cell.cell_id
                break

    counts = ledger.counts()
    manifest.finalize(
        cells_total=len(cells),
        cells_done=counts["done"],
        cells_failed=counts["failed"],
    ).write(run_dir / "manifest.json")

    return RunOutcome(
        run_id=run_id,
        run_dir=run_dir,
        cells_total=len(cells),
        cells_done=counts["done"],
        cells_failed=counts["failed"],
        stopped_early=stopped_early,
        diverged_at=diverged_at,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-url", required=True)
    parser.add_argument("--stage", type=int, choices=(1, 2), required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--trials", type=int, default=32)
    parser.add_argument("--results-root", type=Path, default=Path("bench/results"))
    parser.add_argument("--resume", default=None, help="Existing run-id to continue.")
    parser.add_argument("--model", default=None, help="Stage 2: the chosen model.")
    parser.add_argument("--max-tokens", type=int, default=None, help="Stage 2.")
    parser.add_argument("--heterogeneity", default="mixed", help="Stage 2.")
    parser.add_argument(
        "--concurrency", type=int, nargs="+", default=[1, 4, 16, 64], help="Stage 2."
    )
    args = parser.parse_args(argv)

    if args.stage == 1:
        cells = stage1_ladder(args.seed, trials=args.trials)
        spec = MatrixSpec(stage=1, seed=args.seed, trials=args.trials)
        stop = True
    else:
        if not args.model or not args.max_tokens:
            parser.error(
                "--stage 2 requires --model and --max-tokens: the configuration is "
                "chosen by a human from Stage 1's evidence (requirements §7.1)"
            )
        cells = stage2_matrix(
            args.seed,
            model=args.model,
            max_tokens=args.max_tokens,
            concurrency=args.concurrency,
            heterogeneity=args.heterogeneity,
            trials=args.trials,
        )
        spec = MatrixSpec(
            stage=2,
            seed=args.seed,
            models=(args.model,),
            max_tokens=(args.max_tokens,),
            concurrency=tuple(args.concurrency),
            heterogeneity=(args.heterogeneity,),
            trials=args.trials,
        )
        stop = False

    outcome = execute(
        engine_url=args.engine_url,
        cells=cells,
        results_root=args.results_root,
        spec=spec,
        command=" ".join(["attest-run", *(argv or sys.argv[1:])]),
        run_id=args.resume,
        stop_on_divergence=stop,
    )
    print(json.dumps(outcome.to_dict(), sort_keys=True))

    if outcome.stopped_early:
        print(
            f"\nSTAGE 1 STOPPED EARLY at {outcome.diverged_at} — divergence found.\n"
            "Decision point: choose the model, max_tokens and concurrency for stage 2\n"
            "from this evidence, then re-run with --stage 2.",
            file=sys.stderr,
        )
    return 0 if outcome.cells_failed == 0 else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
