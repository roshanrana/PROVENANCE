"""Every row of the LLD §5 exit-code taxonomy gets a test.

The point of the taxonomy is that a validator can tell *tampered* from *corrupt*
from *offline*. A test suite that only proves "invalid receipts fail" would let
those collapse into each other without anyone noticing.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from attest.receipt import cli
from attest.receipt.provenance import HubUnreachable, resolve_model_identity
from attest.receipt.sign import (
    generate_private_key,
    sign_statement,
    write_public_key,
)
from attest.receipt.sign import (
    test_private_key as fixture_private_key,
)
from tests.attest.test_receipt_schema import make_receipt


def _write_bundle(
    tmp_path: Path,
    *,
    use_test_key: bool = False,
    statement: dict[str, Any] | None = None,
) -> Path:
    key = fixture_private_key() if use_test_key else generate_private_key()
    doc = statement if statement is not None else make_receipt().to_statement()
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    sig = sign_statement(doc, key, allow_test_key=use_test_key)
    receipt.with_suffix(".sig").write_bytes(sig)
    write_public_key(key.public_key(), tmp_path / "pubkey.ed25519")
    return receipt


def run(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    code = cli.main(list(argv), out=out)
    return code, out.getvalue()


# --------------------------------------------------------------------------- 0


def test_valid_receipt_exits_zero(tmp_path: Path) -> None:
    receipt = _write_bundle(tmp_path)
    code, text = run("verify", str(receipt))
    assert code == cli.EXIT_OK
    assert text.startswith("OK attest-20260829T143005Z-abc1234/c0001")


def test_reformatting_the_file_does_not_break_verification(tmp_path: Path) -> None:
    """Canonicalisation is recomputed from the parsed document, not the bytes.

    A receipt that stops verifying because someone pretty-printed it would be
    useless in practice.
    """
    receipt = _write_bundle(tmp_path)
    doc = json.loads(receipt.read_text())
    receipt.write_text(json.dumps(doc, indent=8, sort_keys=True), encoding="utf-8")
    assert run("verify", str(receipt))[0] == cli.EXIT_OK


# --------------------------------------------------------------------------- 2


def test_bad_signature_exits_two(tmp_path: Path) -> None:
    receipt = _write_bundle(tmp_path)
    sig = receipt.with_suffix(".sig")
    corrupted = bytearray(sig.read_bytes())
    corrupted[0] ^= 0xFF
    sig.write_bytes(bytes(corrupted))
    code, text = run("verify", str(receipt))
    assert code == cli.EXIT_SIGNATURE_INVALID
    assert "SIGNATURE INVALID" in text


def test_signature_from_a_different_key_exits_two(tmp_path: Path) -> None:
    receipt = _write_bundle(tmp_path)
    other = generate_private_key()
    write_public_key(other.public_key(), tmp_path / "pubkey.ed25519")
    assert run("verify", str(receipt))[0] == cli.EXIT_SIGNATURE_INVALID


# --------------------------------------------------------------------------- 3


def test_edited_output_exits_three_not_four(tmp_path: Path) -> None:
    """Tampering must be distinguishable from corruption."""
    doc = make_receipt().to_statement()
    receipt = _write_bundle(tmp_path, statement=doc)
    edited = json.loads(receipt.read_text())
    edited["predicate"]["output"]["token_ids"] = [1, 2, 3]
    receipt.write_text(json.dumps(edited), encoding="utf-8")
    code, text = run("verify", str(receipt))
    assert code == cli.EXIT_DIGEST_MISMATCH
    assert "DIGEST MISMATCH" in text


# --------------------------------------------------------------------------- 4


def test_invalid_json_exits_four(tmp_path: Path) -> None:
    receipt = _write_bundle(tmp_path)
    receipt.write_text("{not json", encoding="utf-8")
    code, text = run("verify", str(receipt))
    assert code == cli.EXIT_MALFORMED
    assert "MALFORMED" in text


def test_missing_receipt_exits_four(tmp_path: Path) -> None:
    code, text = run("verify", str(tmp_path / "absent.json"))
    assert code == cli.EXIT_MALFORMED
    assert "no such receipt" in text


def test_missing_signature_exits_four(tmp_path: Path) -> None:
    receipt = _write_bundle(tmp_path)
    receipt.with_suffix(".sig").unlink()
    assert run("verify", str(receipt))[0] == cli.EXIT_MALFORMED


def test_unknown_field_exits_four(tmp_path: Path) -> None:
    doc = make_receipt().to_statement()
    doc["predicate"]["engine"]["undocumented"] = True
    receipt = _write_bundle(tmp_path, statement=doc)
    code, text = run("verify", str(receipt))
    assert code == cli.EXIT_MALFORMED
    assert "undocumented" in text


# --------------------------------------------------------------------------- 5 / 6


def test_hub_unreachable_exits_five_and_says_offline_passed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one sanctioned degradation: offline still gets an answer."""
    receipt = _write_bundle(tmp_path)
    monkeypatch.setenv("PROVENANCE_HF_OFFLINE", "1")
    code, text = run("verify", str(receipt), "--online")
    assert code == cli.EXIT_HUB_UNREACHABLE
    assert "offline verification passed" in text


def test_identity_divergence_exits_six(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    receipt = _write_bundle(tmp_path)
    from attest.receipt import provenance as prov

    def fake(repo_id: str, **_: object) -> prov.HubIdentity:
        return prov.HubIdentity(repo_id, "0" * 40, "model.safetensors", "f" * 64)

    monkeypatch.setattr(prov, "resolve_model_identity", fake)
    code, text = run("verify", str(receipt), "--online")
    assert code == cli.EXIT_IDENTITY_DIVERGENT
    assert "commit_sha" in text


def test_identity_agreement_exits_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    receipt = _write_bundle(tmp_path)
    from attest.receipt import provenance as prov

    def fake(repo_id: str, **_: object) -> prov.HubIdentity:
        return prov.HubIdentity(
            repo_id,
            "7ae557604adf67be50417f59c2c2f167def9a775",
            "model.safetensors",
            "f" * 64,
        )

    monkeypatch.setattr(prov, "resolve_model_identity", fake)
    assert run("verify", str(receipt), "--online")[0] == cli.EXIT_OK


# --------------------------------------------------------------------------- 7


def test_test_key_receipt_is_refused_by_default(tmp_path: Path) -> None:
    receipt = _write_bundle(tmp_path, use_test_key=True)
    code, text = run("verify", str(receipt))
    assert code == cli.EXIT_TEST_KEY
    assert "REFUSING: test key" in text


def test_test_key_receipt_is_accepted_when_explicitly_allowed(tmp_path: Path) -> None:
    receipt = _write_bundle(tmp_path, use_test_key=True)
    assert run("verify", str(receipt), "--allow-test-key")[0] == cli.EXIT_OK


# --------------------------------------------------------------------------- provenance


def test_offline_env_short_circuits_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROVENANCE_HF_OFFLINE", "1")
    with pytest.raises(HubUnreachable, match="OFFLINE"):
        resolve_model_identity("Qwen/Qwen2.5-0.5B-Instruct")


def test_resolution_extracts_commit_sha_and_lfs_digest() -> None:
    payload = {
        "sha": "7ae557604adf67be50417f59c2c2f167def9a775",
        "siblings": [
            {"rfilename": "config.json"},
            {"rfilename": "model.safetensors", "lfs": {"sha256": "b" * 64}},
        ],
    }
    transport = httpx.MockTransport(lambda _req: httpx.Response(200, json=payload))
    with httpx.Client(transport=transport) as client:
        identity = resolve_model_identity("Qwen/Qwen2.5-0.5B-Instruct", client=client)
    assert identity.commit_sha == payload["sha"]
    assert identity.weights_lfs_sha256 == "b" * 64


def test_http_error_becomes_hub_unreachable() -> None:
    transport = httpx.MockTransport(lambda _req: httpx.Response(503))
    with httpx.Client(transport=transport) as client, pytest.raises(HubUnreachable):
        resolve_model_identity("Qwen/Qwen2.5-0.5B-Instruct", client=client)


def test_weights_without_lfs_digest_is_unreachable_not_silently_empty() -> None:
    payload = {"sha": "a" * 40, "siblings": [{"rfilename": "model.safetensors"}]}
    transport = httpx.MockTransport(lambda _req: httpx.Response(200, json=payload))
    with (
        httpx.Client(transport=transport) as client,
        pytest.raises(HubUnreachable, match="LFS sha256"),
    ):
        resolve_model_identity("Qwen/Qwen2.5-0.5B-Instruct", client=client)
