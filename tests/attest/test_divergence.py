from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from attest.analysis.divergence import (
    IncompleteMatrix,
    Observation,
    analyse_run,
    read_observations,
    summarise_cell,
    to_markdown_table,
)
from attest.harness.ledger import Ledger


def _obs(cell: str, trial: int, tokens: tuple[int, ...], digest: str) -> Observation:
    return Observation(cell_id=cell, trial=trial, token_ids=tokens, logprobs_sha256=digest)


def _write_cell(run_dir: Path, cell_id: str, rows: list[tuple[tuple[int, ...], str]]) -> None:
    with open(run_dir / f"{cell_id}.jsonl", "w", encoding="utf-8") as fh:
        for i, (tokens, digest) in enumerate(rows):
            fh.write(
                json.dumps(
                    {
                        "cell_id": cell_id,
                        "trial": i,
                        "token_ids": list(tokens),
                        "logprobs_sha256": digest,
                    }
                )
                + "\n"
            )


def _run(
    tmp_path: Path,
    cells: dict[str, tuple[dict[str, Any], list[tuple[tuple[int, ...], str]]]],
) -> Path:
    run_dir = tmp_path / "attest-20260829T000000Z-abc1234"
    run_dir.mkdir(parents=True)
    ledger = Ledger.in_dir(run_dir)
    ledger.seed([{"cell_id": cid, "params": p} for cid, (p, _) in cells.items()])
    for cell_id, (_, rows) in cells.items():
        _write_cell(run_dir, cell_id, rows)
        ledger.mark_done(cell_id, f"{cell_id}.jsonl")
    return run_dir


# --------------------------------------------------------------------------- cell level


def test_identical_trials_are_one_completion() -> None:
    obs = [_obs("c1", i, (1, 2, 3), "a" * 64) for i in range(8)]
    summary = summarise_cell("c1", {"concurrency": 8}, obs)
    assert summary.unique_completions == 1
    assert summary.bitwise_identical


def test_differing_tokens_are_counted_as_divergence() -> None:
    obs = [_obs("c1", 0, (1, 2, 3), "a" * 64), _obs("c1", 1, (1, 2, 4), "b" * 64)]
    assert summarise_cell("c1", {}, obs).unique_completions == 2


def test_identical_tokens_with_differing_logprobs_is_still_divergence() -> None:
    """The bits move before the words do.

    Two completions can render identical text from different logprobs. Comparing
    only tokens would report that run as reproducible, which is precisely the
    overclaim FR-A-03 must not make.
    """
    obs = [_obs("c1", 0, (1, 2, 3), "a" * 64), _obs("c1", 1, (1, 2, 3), "b" * 64)]
    summary = summarise_cell("c1", {}, obs)
    assert summary.unique_completions == 2
    assert summary.unique_token_sequences == 1
    assert not summary.bitwise_identical


def test_empty_cell_is_refused() -> None:
    with pytest.raises(ValueError, match="no observations"):
        summarise_cell("c1", {}, [])


# --------------------------------------------------------------------------- run level


def test_divergence_is_reported_when_present(tmp_path: Path) -> None:
    run_dir = _run(
        tmp_path,
        {
            "c0000": (
                {"batch_invariant": False, "concurrency": 16, "model": "qwen"},
                [((1, 2), "a" * 64), ((1, 3), "b" * 64), ((1, 4), "c" * 64)],
            )
        },
    )
    report = analyse_run(run_dir)
    assert report.divergence_observed()
    assert report.cells[0].unique_completions == 3
    assert "divergence observed: up to 3" in "\n".join(report.summary_lines())


def test_no_divergence_is_a_publishable_result(tmp_path: Path) -> None:
    """NFR-17. An absent effect is a finding, stated plainly, not a silent gap."""
    run_dir = _run(
        tmp_path,
        {"c0000": ({"batch_invariant": False, "concurrency": 64}, [((1, 2), "a" * 64)] * 5)},
    )
    report = analyse_run(run_dir)
    assert not report.divergence_observed()
    assert "NO divergence observed" in "\n".join(report.summary_lines())


def test_reproducibility_holds_when_invariance_on_cells_are_identical(
    tmp_path: Path,
) -> None:
    run_dir = _run(
        tmp_path,
        {
            "c0000": ({"batch_invariant": False}, [((1, 2), "a" * 64), ((1, 3), "b" * 64)]),
            "c0001": ({"batch_invariant": True}, [((9, 9), "z" * 64)] * 6),
        },
    )
    report = analyse_run(run_dir)
    assert report.divergence_observed()
    assert report.reproducibility_holds()


def test_reproducibility_failure_names_the_cell(tmp_path: Path) -> None:
    run_dir = _run(
        tmp_path,
        {"c0001": ({"batch_invariant": True}, [((9, 9), "z" * 64), ((9, 8), "y" * 64)])},
    )
    report = analyse_run(run_dir)
    assert not report.reproducibility_holds()
    assert "REPRODUCIBILITY FAILED in: c0001" in "\n".join(report.summary_lines())


def test_an_empty_invariance_sweep_does_not_read_as_a_proof(tmp_path: Path) -> None:
    """`reproducibility_holds` is vacuously true with no cells. Say so."""
    run_dir = _run(tmp_path, {"c0000": ({"batch_invariant": False}, [((1, 2), "a" * 64)] * 3)})
    report = analyse_run(run_dir)
    assert report.reproducibility_holds()  # vacuous
    assert "reproducibility was not tested" in "\n".join(report.summary_lines())


# --------------------------------------------------------------------------- refusals


def test_unfinished_matrix_is_refused(tmp_path: Path) -> None:
    run_dir = tmp_path / "attest-20260829T000000Z-abc1234"
    run_dir.mkdir(parents=True)
    ledger = Ledger.in_dir(run_dir)
    ledger.seed([{"cell_id": "c0000", "params": {}}, {"cell_id": "c0001", "params": {}}])
    _write_cell(run_dir, "c0000", [((1, 2), "a" * 64)])
    ledger.mark_done("c0000", "c0000.jsonl")  # c0001 left pending

    with pytest.raises(IncompleteMatrix, match="unfinished"):
        analyse_run(run_dir)


def test_failed_cell_blocks_the_headline_number(tmp_path: Path) -> None:
    """A mean over the cells that happened to survive is survivor bias."""
    run_dir = tmp_path / "attest-20260829T000000Z-abc1234"
    run_dir.mkdir(parents=True)
    ledger = Ledger.in_dir(run_dir)
    ledger.seed([{"cell_id": "c0000", "params": {}}])
    ledger.mark_failed("c0000", "CUDA OOM")

    with pytest.raises(IncompleteMatrix, match="failed"):
        analyse_run(run_dir)


def test_missing_raw_file_is_refused(tmp_path: Path) -> None:
    run_dir = tmp_path / "attest-20260829T000000Z-abc1234"
    run_dir.mkdir(parents=True)
    ledger = Ledger.in_dir(run_dir)
    ledger.seed([{"cell_id": "c0000", "params": {}}])
    ledger.mark_done("c0000", "c0000.jsonl")  # never written

    with pytest.raises(IncompleteMatrix, match="missing"):
        analyse_run(run_dir)


def test_empty_ledger_is_refused(tmp_path: Path) -> None:
    run_dir = tmp_path / "empty"
    run_dir.mkdir()
    with pytest.raises(IncompleteMatrix, match="empty"):
        analyse_run(run_dir)


def test_malformed_observation_line_is_an_error(tmp_path: Path) -> None:
    """Analysis of published numbers does not get to shrug at bad input."""
    path = tmp_path / "c0000.jsonl"
    path.write_text('{"cell_id": "c0000", "token_ids": [1]}\n')  # no logprobs_sha256
    with pytest.raises(ValueError, match="unusable observation"):
        read_observations(path)


# --------------------------------------------------------------------------- rendering


def test_markdown_table_has_a_row_per_cell(tmp_path: Path) -> None:
    run_dir = _run(
        tmp_path,
        {
            "c0000": ({"batch_invariant": False, "concurrency": 1}, [((1,), "a" * 64)]),
            "c0001": ({"batch_invariant": True, "concurrency": 8}, [((1,), "a" * 64)]),
        },
    )
    table = to_markdown_table(analyse_run(run_dir))
    assert table.count("\n") == 3  # header + separator + 2 rows
    assert "| yes |" in table and "| no |" in table


def test_report_serialises_its_conclusions(tmp_path: Path) -> None:
    run_dir = _run(
        tmp_path,
        {"c0000": ({"batch_invariant": False}, [((1,), "a" * 64), ((2,), "b" * 64)])},
    )
    doc = analyse_run(run_dir).to_dict()
    assert doc["divergence_observed"] is True
    assert doc["n_cells_invariance_off"] == 1
    assert doc["cells"][0]["unique_completions"] == 2
