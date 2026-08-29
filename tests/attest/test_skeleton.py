"""M0 walking skeleton — the seams, tested.

These are integration tests in the sense that matters here: they cross every
boundary of the real architecture (ledger → engine → raw output → receipt →
signature → manifest) with only the engine faked. No GPU, no cluster.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from attest.harness.engine import EngineClient, EngineError, logprobs_digest
from attest.harness.ledger import CellState, Ledger
from attest.harness.skeleton import run_skeleton
from attest.receipt import cli
from attest.receipt.schema import Receipt, SamplingParams
from common.runid import Manifest
from tests.support.stub_engine import StubConfig, stub_engine

GIT = ("abc1234", False)

pytestmark = pytest.mark.integration


def _run(tmp_path: Path, **kw: object) -> object:
    with stub_engine(StubConfig(divergence_mode="none")) as stub:
        return run_skeleton(
            engine_url=stub.url,
            results_root=tmp_path,
            use_test_key=True,
            git=GIT,
            **kw,  # type: ignore[arg-type]
        )


def test_skeleton_produces_every_artefact(tmp_path: Path) -> None:
    result = _run(tmp_path)
    run_dir = result.run_dir  # type: ignore[attr-defined]
    for name in (
        "manifest.json",
        "cells.jsonl",
        "c0001.jsonl",
        "receipts/receipt.json",
        "receipts/receipt.sig",
        "receipts/pubkey.ed25519",
    ):
        assert (run_dir / name).exists(), f"missing artefact: {name}"


def test_receipt_verifies_through_the_shipped_cli(tmp_path: Path) -> None:
    """Verify through the CLI, not in-process: the exit-code contract is the deliverable."""
    result = _run(tmp_path)
    receipt = result.receipt_path  # type: ignore[attr-defined]
    assert cli.main(["verify", str(receipt), "--allow-test-key"]) == cli.EXIT_OK


def test_unsigned_fixture_receipt_is_refused_without_the_flag(tmp_path: Path) -> None:
    result = _run(tmp_path)
    receipt = result.receipt_path  # type: ignore[attr-defined]
    assert cli.main(["verify", str(receipt)]) == cli.EXIT_TEST_KEY


def test_ledger_records_a_completed_cell(tmp_path: Path) -> None:
    result = _run(tmp_path)
    ledger = Ledger.in_dir(result.run_dir)  # type: ignore[attr-defined]
    assert ledger.states()["c0001"].state is CellState.DONE
    assert ledger.is_complete()
    assert ledger.counts()["failed"] == 0


def test_manifest_is_finalised_with_counts(tmp_path: Path) -> None:
    result = _run(tmp_path)
    manifest = Manifest.read(result.run_dir / "manifest.json")  # type: ignore[attr-defined]
    assert manifest.cells_total == 1
    assert manifest.cells_done == 1
    assert manifest.finished_utc is not None
    assert manifest.git_sha == "abc1234"


def test_receipt_binds_resolved_config_not_the_request(tmp_path: Path) -> None:
    """D-08. The stub resolves values the caller never asked for; they must appear."""
    result = _run(tmp_path)
    doc = json.loads(Path(result.receipt_path).read_text())  # type: ignore[attr-defined]
    engine = doc["predicate"]["engine"]
    assert engine["resolved_config"]["cudagraph_mode"] == "PIECEWISE"
    assert engine["attention_backend"] == "FLASH_ATTN"
    assert engine["tensor_parallel_size"] == 1


def test_receipt_is_written_canonically(tmp_path: Path) -> None:
    """Bytes on disk are already canonical, so signature checks are byte-stable."""
    from attest.receipt.canonical import canonical_bytes

    result = _run(tmp_path)
    raw = Path(result.receipt_path).read_bytes()  # type: ignore[attr-defined]
    assert raw == canonical_bytes(json.loads(raw))


def test_receipt_parses_back_into_the_frozen_type(tmp_path: Path) -> None:
    result = _run(tmp_path)
    doc = json.loads(Path(result.receipt_path).read_text())  # type: ignore[attr-defined]
    receipt = Receipt.from_statement(doc)
    assert receipt.run.cell_id == "c0001"
    assert receipt.model.resolution == "unresolved"  # honest: no network in M0


def test_run_dir_name_carries_provenance(tmp_path: Path) -> None:
    result = _run(tmp_path)
    assert result.run_dir.name.startswith("attest-")  # type: ignore[attr-defined]
    assert result.run_dir.name.endswith("-abc1234")  # type: ignore[attr-defined]


def test_engine_failure_marks_the_cell_failed_and_reraises(tmp_path: Path) -> None:
    """Fail fast and loudly. A silently degraded run produces a plausible wrong number."""
    with pytest.raises(EngineError):
        run_skeleton(
            engine_url="http://127.0.0.1:1",  # nothing listening
            results_root=tmp_path,
            use_test_key=True,
            git=GIT,
        )
    run_dirs = list(tmp_path.iterdir())
    assert len(run_dirs) == 1
    ledger = Ledger.in_dir(run_dirs[0])
    assert ledger.states()["c0001"].state is CellState.FAILED
    manifest = Manifest.read(run_dirs[0] / "manifest.json")
    assert manifest.cells_failed == 1 and manifest.cells_done == 0


def test_logprobs_digest_is_bitwise_not_rounded() -> None:
    """FR-A-03 claims bitwise identity; a tolerant digest would weaken the claim.

    ``nextafter`` gives the smallest representable change — one ULP. If the digest
    cannot see that, it cannot support a bitwise claim.
    """
    import math

    one_ulp_away = math.nextafter(0.2, math.inf)
    assert one_ulp_away != 0.2
    assert logprobs_digest([0.1, 0.2]) != logprobs_digest([0.1, one_ulp_away])
    assert logprobs_digest([0.1, 0.2]) == logprobs_digest([0.1, 0.2])
    # -0.0 and 0.0 compare equal but are different bit patterns; a bitwise
    # digest must distinguish them.
    assert logprobs_digest([0.0]) != logprobs_digest([-0.0])


def test_engine_client_reports_unusable_payloads(tmp_path: Path) -> None:
    with stub_engine() as stub, EngineClient(stub.url) as engine:
        with pytest.raises(EngineError, match=r"no such path|failed"):
            engine._get("/definitely-not-here")
        sampling = SamplingParams(seed=0, temperature=0.0, top_p=1.0, max_tokens=4)
        assert len(engine.complete("x", sampling).token_ids) == 4
