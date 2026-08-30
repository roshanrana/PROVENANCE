"""The run driver — resumability is the property that matters.

FR-A-09 exists because the ATTEST matrix runs once, on rented hardware, over a
paid session that can drop. Every test here is really asking the same question:
after an interruption, does the run resume without repeating work or losing it?
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from attest.harness.ledger import CellState, Ledger
from attest.harness.matrix import Cell, MatrixSpec, stage2_matrix
from attest.harness.run import execute, run_cell
from common.runid import Manifest
from tests.support.stub_engine import StubConfig, stub_engine

GIT = ("abc1234", False)

pytestmark = pytest.mark.integration


def _cells(trials: int = 4, concurrency: tuple[int, ...] = (1, 4)) -> list[Cell]:
    return stage2_matrix(
        seed=1,
        model="Qwen/Qwen2.5-0.5B-Instruct",
        max_tokens=8,
        concurrency=concurrency,
        heterogeneity="uniform",
        trials=trials,
    )


def _spec() -> MatrixSpec:
    return MatrixSpec(stage=2, seed=1, models=("m",), max_tokens=(8,), trials=4)


def _execute(tmp_path: Path, stub_url: str, **kw: object) -> object:
    return execute(
        engine_url=stub_url,
        cells=_cells(),
        results_root=tmp_path,
        spec=_spec(),
        command="test",
        git=GIT,
        **kw,  # type: ignore[arg-type]
    )


def test_run_completes_every_cell(tmp_path: Path) -> None:
    with stub_engine(StubConfig(divergence_mode="none")) as stub:
        outcome = _execute(tmp_path, stub.url)
    assert outcome.cells_failed == 0  # type: ignore[attr-defined]
    assert outcome.cells_done == outcome.cells_total  # type: ignore[attr-defined]
    assert Ledger.in_dir(outcome.run_dir).is_complete()  # type: ignore[attr-defined]


def test_raw_output_is_written_per_cell(tmp_path: Path) -> None:
    with stub_engine() as stub:
        outcome = _execute(tmp_path, stub.url)
    run_dir = outcome.run_dir  # type: ignore[attr-defined]
    for cell in _cells():
        path = run_dir / f"{cell.cell_id}.jsonl"
        assert path.exists()
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        assert len(rows) == cell.params.trials
        assert [r["trial"] for r in rows] == sorted(r["trial"] for r in rows)
        assert all("logprobs_sha256" in r for r in rows)


def test_matrix_spec_is_committed_alongside_results(tmp_path: Path) -> None:
    """NFR-01: a reader must be able to tell what experiment produced these numbers."""
    with stub_engine() as stub:
        outcome = _execute(tmp_path, stub.url)
    doc = json.loads((outcome.run_dir / "matrix.json").read_text())  # type: ignore[attr-defined]
    assert doc["spec"]["stage"] == 2
    assert len(doc["fingerprint"]) == 16


def test_manifest_records_final_counts(tmp_path: Path) -> None:
    with stub_engine() as stub:
        outcome = _execute(tmp_path, stub.url)
    manifest = Manifest.read(outcome.run_dir / "manifest.json")  # type: ignore[attr-defined]
    assert manifest.cells_done == outcome.cells_total  # type: ignore[attr-defined]
    assert manifest.finished_utc is not None


# --------------------------------------------------------------------------- resume


def test_resume_skips_completed_cells(tmp_path: Path) -> None:
    """The property FR-A-09 exists for: paid GPU work is never redone."""
    cells = _cells()
    with stub_engine() as stub:
        first = _execute(tmp_path, stub.url)
        run_dir = first.run_dir  # type: ignore[attr-defined]

        # Record what the first pass wrote, then resume onto the same run.
        before = {c.cell_id: (run_dir / f"{c.cell_id}.jsonl").read_text() for c in cells}
        requests_after_first = stub.state.requests

        second = execute(
            engine_url=stub.url,
            cells=cells,
            results_root=tmp_path,
            spec=_spec(),
            command="test",
            git=GIT,
            run_id=first.run_id,  # type: ignore[attr-defined]
        )
        # Nothing re-ran: the engine saw no further traffic.
        assert stub.state.requests == requests_after_first

    assert second.cells_done == first.cells_done  # type: ignore[attr-defined]
    after = {c.cell_id: (run_dir / f"{c.cell_id}.jsonl").read_text() for c in cells}
    assert before == after


def test_interrupted_cell_is_re_run_on_resume(tmp_path: Path) -> None:
    """A cell left `running` is assumed interrupted and must be redone."""
    cells = _cells()
    with stub_engine() as stub:
        outcome = _execute(tmp_path, stub.url)
        run_dir = outcome.run_dir  # type: ignore[attr-defined]

        # Simulate a drop mid-cell: mark one cell running again.
        victim = cells[0].cell_id
        Ledger.in_dir(run_dir).mark_running(victim)
        assert victim in {r.cell_id for r in Ledger.in_dir(run_dir).resumable()}

        before = stub.state.requests
        execute(
            engine_url=stub.url,
            cells=cells,
            results_root=tmp_path,
            spec=_spec(),
            command="test",
            git=GIT,
            run_id=outcome.run_id,  # type: ignore[attr-defined]
        )
        assert stub.state.requests > before  # exactly that cell re-ran

    assert Ledger.in_dir(run_dir).states()[victim].state is CellState.DONE


def test_failed_cell_is_not_retried_on_resume(tmp_path: Path) -> None:
    """HLD §8.4: retrying until success is how survivor bias enters a table."""
    cells = _cells()
    with stub_engine() as stub:
        outcome = _execute(tmp_path, stub.url)
        run_dir = outcome.run_dir  # type: ignore[attr-defined]
        Ledger.in_dir(run_dir).mark_failed(cells[0].cell_id, "simulated OOM")

        before = stub.state.requests
        second = execute(
            engine_url=stub.url,
            cells=cells,
            results_root=tmp_path,
            spec=_spec(),
            command="test",
            git=GIT,
            run_id=outcome.run_id,  # type: ignore[attr-defined]
        )
        assert stub.state.requests == before  # nothing re-ran

    assert second.cells_failed == 1
    assert Ledger.in_dir(run_dir).states()[cells[0].cell_id].state is CellState.FAILED


def test_resuming_a_missing_run_is_refused(tmp_path: Path) -> None:
    with stub_engine() as stub, pytest.raises(FileNotFoundError, match="cannot resume"):
        _execute(tmp_path, stub.url, run_id="attest-20260101T000000Z-0000000")


# --------------------------------------------------------------------------- failures


def test_engine_failure_marks_the_cell_and_continues(tmp_path: Path) -> None:
    """One bad cell must not abandon a paid session's remaining work."""
    outcome = execute(
        engine_url="http://127.0.0.1:1",  # nothing listening
        cells=_cells(),
        results_root=tmp_path,
        spec=_spec(),
        command="test",
        git=GIT,
    )
    assert outcome.cells_failed == outcome.cells_total
    assert outcome.cells_done == 0
    states = Ledger.in_dir(outcome.run_dir).states()
    assert all(s.state is CellState.FAILED for s in states.values())
    assert all("EngineError" in (s.error or "") for s in states.values())


# --------------------------------------------------------------------------- stage 1


def test_stage_one_stops_early_once_divergence_appears(tmp_path: Path) -> None:
    """GPU minutes spent confirming a known effect are minutes not spent finding it."""
    cells = _cells(trials=8, concurrency=(16,))
    with stub_engine(StubConfig(divergence_mode="random")) as stub:
        outcome = execute(
            engine_url=stub.url,
            cells=cells,
            results_root=tmp_path,
            spec=_spec(),
            command="test",
            git=GIT,
            stop_on_divergence=True,
        )
    assert outcome.stopped_early
    assert outcome.diverged_at is not None
    assert outcome.cells_done < outcome.cells_total


def test_no_early_stop_when_output_is_stable(tmp_path: Path) -> None:
    cells = _cells(trials=4, concurrency=(1, 4))
    with stub_engine(StubConfig(divergence_mode="none")) as stub:
        outcome = execute(
            engine_url=stub.url,
            cells=cells,
            results_root=tmp_path,
            spec=_spec(),
            command="test",
            git=GIT,
            stop_on_divergence=True,
        )
    assert not outcome.stopped_early
    assert outcome.cells_done == outcome.cells_total


def test_run_cell_writes_trials_in_order(tmp_path: Path) -> None:
    """Concurrent execution, deterministic file order — so diffs are readable."""
    cell = _cells(trials=6, concurrency=(4,))[0]
    with stub_engine() as stub:
        records = run_cell(stub.url, cell, tmp_path)
    assert len(records) == 6
    rows = [
        json.loads(line) for line in (tmp_path / f"{cell.cell_id}.jsonl").read_text().splitlines()
    ]
    assert [r["trial"] for r in rows] == list(range(6))
