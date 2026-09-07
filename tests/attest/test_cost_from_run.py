"""The join between a run directory and the cost analysis.

The analysis could always compute the figure; nothing fed it. These tests are
mostly about the refusals, because a cost-of-determinism number built from the
wrong samples is worse than no number — it is publishable and wrong.
"""

from __future__ import annotations

import json
from pathlib import Path

from attest.analysis.cost_from_run import load_arms


def _write(run_dir: Path, cell: str, invariant: bool, latencies: list[float]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(run_dir / "cells.jsonl", "a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "cell_id": cell,
                    "state": "done",
                    "params": {
                        "batch_invariant": invariant,
                        "concurrency": 16,
                        "model": "m",
                        "max_tokens": 64,
                    },
                }
            )
            + "\n"
        )
    with open(run_dir / f"{cell}.jsonl", "w", encoding="utf-8") as fh:
        for i, latency in enumerate(latencies):
            fh.write(
                json.dumps(
                    {
                        "cell_id": cell,
                        "trial": i,
                        "latency_s": latency,
                        "output_tokens": 64,
                        "tokens_per_s": 64.0 / latency,
                        "logprobs_sha256": "a" * 64,
                    }
                )
                + "\n"
            )


def test_arms_split_on_the_ledgers_recorded_setting(tmp_path: Path) -> None:
    _write(tmp_path, "c0000", False, [0.1, 0.2])
    _write(tmp_path, "c0001", True, [0.3, 0.4])
    off, on = load_arms(tmp_path)
    assert off["latency_s"] == [0.1, 0.2]
    assert on["latency_s"] == [0.3, 0.4]
    # batch_invariant is the variable under test, so it must not appear in the
    # conditions the two arms are required to share.
    assert "batch_invariant" not in off["conditions"]
    assert off["conditions"]["concurrency"] == 16


def test_an_arm_that_never_ran_comes_back_empty(tmp_path: Path) -> None:
    """A stage-2 run can legitimately have one arm refused.

    The driver declines cells whose configuration the live engine does not have,
    so an empty arm is a normal state — and reporting one arm against itself
    would be a fabricated comparison, not a cheap one.
    """
    _write(tmp_path, "c0000", False, [0.1, 0.2])
    off, on = load_arms(tmp_path)
    assert off["latency_s"]
    assert on["latency_s"] == []


def test_records_without_timing_are_skipped_not_defaulted(tmp_path: Path) -> None:
    """Runs predating the timing instrumentation must not contribute zeros.

    A fabricated zero latency would drag every bootstrap interval computed from
    it toward a conclusion nobody measured.
    """
    _write(tmp_path, "c0000", False, [0.1])
    with open(tmp_path / "c0000.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"cell_id": "c0000", "trial": 99, "logprobs_sha256": "b" * 64}) + "\n")
    off, _ = load_arms(tmp_path)
    assert off["latency_s"] == [0.1]


def test_an_unlabelled_cell_is_not_guessed_into_an_arm(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "c0000.jsonl").write_text(
        json.dumps({"cell_id": "c0000", "trial": 0, "latency_s": 0.1, "tokens_per_s": 1.0}) + "\n",
        encoding="utf-8",
    )
    off, on = load_arms(tmp_path)
    assert off["latency_s"] == [] and on["latency_s"] == []
