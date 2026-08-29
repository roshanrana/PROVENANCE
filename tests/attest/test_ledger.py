from __future__ import annotations

from pathlib import Path

import pytest

from attest.harness.ledger import CellRecord, CellState, Ledger

CELLS = [
    {"cell_id": "c0001", "params": {"invariant": False, "concurrency": 1}},
    {"cell_id": "c0002", "params": {"invariant": False, "concurrency": 8}},
    {"cell_id": "c0003", "params": {"invariant": True, "concurrency": 8}},
]


def test_seed_writes_pending_records(tmp_path: Path) -> None:
    ledger = Ledger.in_dir(tmp_path)
    ledger.seed(CELLS)
    assert set(ledger.states()) == {"c0001", "c0002", "c0003"}
    assert all(r.state is CellState.PENDING for r in ledger.states().values())


def test_seed_is_idempotent(tmp_path: Path) -> None:
    """Re-running the entry command must not duplicate the matrix."""
    ledger = Ledger.in_dir(tmp_path)
    ledger.seed(CELLS)
    ledger.mark_done("c0001", "out/c0001.jsonl")
    ledger.seed(CELLS)
    assert ledger.states()["c0001"].state is CellState.DONE
    assert len(ledger.states()) == 3


def test_last_transition_wins(tmp_path: Path) -> None:
    ledger = Ledger.in_dir(tmp_path)
    ledger.seed(CELLS)
    ledger.mark_running("c0001")
    ledger.mark_done("c0001", "out/c0001.jsonl")
    record = ledger.states()["c0001"]
    assert record.state is CellState.DONE
    assert record.output_path == "out/c0001.jsonl"


def test_params_survive_transitions(tmp_path: Path) -> None:
    ledger = Ledger.in_dir(tmp_path)
    ledger.seed(CELLS)
    ledger.mark_running("c0002")
    assert ledger.states()["c0002"].params == {"invariant": False, "concurrency": 8}


def test_running_cells_are_resumable_done_cells_are_not(tmp_path: Path) -> None:
    """An interrupted `running` cell must be re-run; a `done` cell must not."""
    ledger = Ledger.in_dir(tmp_path)
    ledger.seed(CELLS)
    ledger.mark_done("c0001", "out/a")
    ledger.mark_running("c0002")  # interrupted here
    resumable = {r.cell_id for r in ledger.resumable()}
    assert resumable == {"c0002", "c0003"}


def test_failed_cells_are_never_resumed(tmp_path: Path) -> None:
    """Excluded from analysis, and never retried into the dataset (HLD §8.4).

    Retrying a failed cell until it succeeds would put a survivor-biased number
    in a published table.
    """
    ledger = Ledger.in_dir(tmp_path)
    ledger.seed(CELLS)
    ledger.mark_failed("c0001", "CUDA OOM")
    assert "c0001" not in {r.cell_id for r in ledger.resumable()}
    assert ledger.states()["c0001"].error == "CUDA OOM"


def test_counts_and_completion(tmp_path: Path) -> None:
    ledger = Ledger.in_dir(tmp_path)
    ledger.seed(CELLS)
    assert not ledger.is_complete()
    ledger.mark_done("c0001", "a")
    ledger.mark_done("c0002", "b")
    ledger.mark_failed("c0003", "boom")
    assert ledger.is_complete()
    assert ledger.counts() == {"pending": 0, "running": 0, "done": 2, "failed": 1}


def test_truncated_final_line_is_dropped_not_fatal(tmp_path: Path) -> None:
    """A power cut mid-write costs the last transition, not the run."""
    ledger = Ledger.in_dir(tmp_path)
    ledger.seed(CELLS)
    ledger.mark_done("c0001", "out/a")
    with open(ledger.path, "a", encoding="utf-8") as fh:
        fh.write('{"cell_id": "c0002", "state": "do')  # torn write
    assert ledger.states()["c0001"].state is CellState.DONE
    assert ledger.states()["c0002"].state is CellState.PENDING


def test_ledger_survives_a_fresh_object(tmp_path: Path) -> None:
    """Resume works across processes — the ledger is the state, not the object."""
    Ledger.in_dir(tmp_path).seed(CELLS)
    Ledger.in_dir(tmp_path).mark_done("c0001", "out/a")
    assert Ledger.in_dir(tmp_path).states()["c0001"].state is CellState.DONE


def test_record_rejects_missing_fields() -> None:
    with pytest.raises(ValueError, match="cell_id"):
        CellRecord.from_dict({"state": "pending", "params": {}})


def test_empty_ledger_reads_as_empty(tmp_path: Path) -> None:
    assert Ledger.in_dir(tmp_path).records() == []
    assert Ledger.in_dir(tmp_path).is_complete()
