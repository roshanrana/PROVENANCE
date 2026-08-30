from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from attest.receipt.schema import (
    PREDICATE_TYPE,
    STATEMENT_TYPE,
    EngineState,
    ModelIdentity,
    OutputRecord,
    Receipt,
    ReceiptSchemaError,
    RunRef,
    SamplingParams,
    subject_digest,
)

GOLDEN = Path(__file__).parent / "golden" / "receipt.json"


def make_receipt(**over: Any) -> Receipt:
    base = dict(
        model=ModelIdentity(
            repo_id="Qwen/Qwen2.5-0.5B-Instruct",
            commit_sha="7ae557604adf67be50417f59c2c2f167def9a775",
            weights_file="model.safetensors",
            weights_lfs_sha256="f" * 64,
            resolution="online",
        ),
        engine=EngineState(
            vllm_version="0.11.0",
            vllm_git_sha="deadbee",
            # D-08: what the engine RESOLVED, not what the operator passed.
            resolved_config={"cudagraph_mode": "PIECEWISE", "enforce_eager": False},
            attention_backend="FLASH_ATTN",
            batch_invariant=True,
            prefix_caching=False,
            speculative_decoding=False,
            tensor_parallel_size=1,
        ),
        sampling=SamplingParams(seed=0, temperature=0.0, top_p=1.0, max_tokens=256),
        output=OutputRecord(
            token_ids=[9707, 11, 1879],
            text="Hello, world",
            logprobs_sha256="a" * 64,
        ),
        run=RunRef(
            run_id="attest-20260829T143005Z-abc1234",
            cell_id="c0001",
            timestamp_utc="2026-08-29T14:30:05Z",
        ),
    )
    base.update(over)
    return Receipt(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- shape


def test_statement_has_the_frozen_shape() -> None:
    doc = make_receipt().to_statement()
    assert doc["_type"] == STATEMENT_TYPE
    assert doc["predicateType"] == PREDICATE_TYPE
    assert set(doc["predicate"]) == {"model", "engine", "sampling", "output", "run"}
    assert doc["subject"][0]["digest"]["sha256"] == subject_digest([9707, 11, 1879])


def test_matches_committed_golden_file() -> None:
    doc = make_receipt().to_statement()
    assert doc == json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_round_trip_is_lossless() -> None:
    r = make_receipt()
    assert Receipt.from_statement(r.to_statement()) == r


def test_model_identity_binds_hub_commit_and_lfs_sha() -> None:
    """D-12: identity anchors to an external root, not a locally computed hash."""
    model = make_receipt().to_statement()["predicate"]["model"]
    assert model["hub"] == "huggingface"
    assert model["commit_sha"] == "7ae557604adf67be50417f59c2c2f167def9a775"
    assert model["weights"]["lfs_sha256"] == "f" * 64


def test_offline_operation_does_not_require_faking_identity() -> None:
    r = make_receipt(
        model=ModelIdentity(
            repo_id="Qwen/Qwen2.5-0.5B-Instruct",
            commit_sha="",
            weights_file="model.safetensors",
            weights_lfs_sha256="",
            resolution="unresolved",
        )
    )
    assert Receipt.from_statement(r.to_statement()).model.resolution == "unresolved"


# --------------------------------------------------------------------------- rejections


def test_unknown_predicate_field_is_rejected_not_ignored() -> None:
    doc = make_receipt().to_statement()
    doc["predicate"]["surprise"] = 1
    with pytest.raises(ReceiptSchemaError, match="surprise"):
        Receipt.from_statement(doc)


def test_unknown_nested_field_is_rejected() -> None:
    doc = make_receipt().to_statement()
    doc["predicate"]["engine"]["extra_flag"] = True
    with pytest.raises(ReceiptSchemaError, match="extra_flag"):
        Receipt.from_statement(doc)


@pytest.mark.parametrize(
    "section,field",
    [
        ("model", "commit_sha"),
        ("engine", "batch_invariant"),
        ("sampling", "seed"),
        ("output", "logprobs_sha256"),
        ("run", "run_id"),
    ],
)
def test_missing_required_field_names_the_field(section: str, field: str) -> None:
    doc = make_receipt().to_statement()
    del doc["predicate"][section][field]
    with pytest.raises(ReceiptSchemaError, match=field):
        Receipt.from_statement(doc)


def test_unknown_predicate_major_version_is_rejected() -> None:
    doc = make_receipt().to_statement()
    doc["predicateType"] = "https://provenance.dev/attestation/v1.0"
    with pytest.raises(ReceiptSchemaError, match="major version"):
        Receipt.from_statement(doc)


def test_same_major_different_minor_is_accepted() -> None:
    doc = make_receipt().to_statement()
    doc["predicateType"] = "https://provenance.dev/attestation/v0.2"
    assert Receipt.from_statement(doc).run.cell_id == "c0001"


def test_foreign_statement_type_is_rejected() -> None:
    doc = make_receipt().to_statement()
    doc["_type"] = "https://example.com/Statement/v1"
    with pytest.raises(ReceiptSchemaError, match="statement type"):
        Receipt.from_statement(doc)


def test_tampered_output_without_matching_subject_digest_is_rejected() -> None:
    """Editing the output but not the subject digest must not parse.

    This is the cheap tamper a verifier must catch even before signature checking.
    """
    doc = make_receipt().to_statement()
    doc["predicate"]["output"]["token_ids"] = [1, 2, 3]
    with pytest.raises(ReceiptSchemaError, match="subject digest"):
        Receipt.from_statement(doc)


def test_unknown_resolution_value_is_rejected() -> None:
    doc = make_receipt().to_statement()
    doc["predicate"]["model"]["resolution"] = "probably-fine"
    with pytest.raises(ReceiptSchemaError, match="resolution"):
        Receipt.from_statement(doc)


def test_multiple_subjects_are_rejected() -> None:
    doc = make_receipt().to_statement()
    doc["subject"].append(copy.deepcopy(doc["subject"][0]))
    with pytest.raises(ReceiptSchemaError, match="single-element"):
        Receipt.from_statement(doc)
