"""Canonicalisation and signing.

This is the layer a `verifier-critical` pass would push hardest on: if the
canonical form is not stable, a valid receipt can fail verification and an
invalid one can pass, and every downstream claim inherits that.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from attest.receipt.canonical import (
    CanonicalizationError,
    canonical_bytes,
    canonicalize,
    recanonicalize,
)
from attest.receipt.sign import (
    SignatureInvalid,
    SigningRefused,
    generate_private_key,
    is_test_key,
    read_private_key,
    read_public_key,
    sign_statement,
    verify_statement,
    write_private_key,
    write_public_key,
)
from attest.receipt.sign import (
    test_private_key as fixture_private_key,
)

# --------------------------------------------------------------------------- scalars


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, "null"),
        (True, "true"),
        (False, "false"),
        (0, "0"),
        (-17, "-17"),
        (1.0, "1"),  # ES6 prints integral doubles without a fraction
        (-0.0, "0"),
        (2.5, "2.5"),
        ("", '""'),
        ("plain", '"plain"'),
    ],
)
def test_scalar_forms(value: object, expected: str) -> None:
    assert canonicalize(value) == expected


def test_bools_are_not_treated_as_numbers() -> None:
    """bool subclasses int in Python. Getting this wrong emits `1` for `true`."""
    assert canonicalize({"flag": True}) == '{"flag":true}'


def test_control_characters_are_escaped() -> None:
    assert canonicalize("a\nb\tc") == '"a\\nb\\tc"'
    assert canonicalize("\x01") == '"\\u0001"'


def test_quotes_and_backslashes_are_escaped() -> None:
    assert canonicalize('he said "hi"\\') == '"he said \\"hi\\"\\\\"'


def test_non_ascii_is_not_escaped() -> None:
    """RFC 8785 emits UTF-8 directly rather than \\u escapes."""
    assert canonicalize("ünïcødé") == '"ünïcødé"'


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_numbers_are_refused(bad: float) -> None:
    """A field that cannot round-trip is not evidence of anything."""
    with pytest.raises(CanonicalizationError):
        canonicalize(bad)


def test_unsupported_type_is_refused() -> None:
    with pytest.raises(CanonicalizationError, match="cannot canonicalise"):
        canonicalize({1, 2, 3})


def test_non_string_keys_are_refused() -> None:
    with pytest.raises(CanonicalizationError, match="keys must be strings"):
        canonicalize({1: "a"})


# --------------------------------------------------------------------------- ordering


def test_keys_are_sorted_deterministically() -> None:
    assert canonicalize({"b": 1, "a": 2, "c": 3}) == '{"a":2,"b":1,"c":3}'


def test_key_order_of_the_input_does_not_matter() -> None:
    a = canonicalize({"z": 1, "a": {"y": 2, "b": 3}})
    b = canonicalize({"a": {"b": 3, "y": 2}, "z": 1})
    assert a == b


def test_sorting_is_by_utf16_code_units_not_python_default() -> None:
    """RFC 8785 sorts by UTF-16 code units.

    Above the BMP the two orders differ: U+1F600 is a surrogate pair starting
    0xD83D, which sorts *below* U+FF01. Python's default str comparison puts it
    above. Getting this wrong makes our canonical form disagree with every other
    RFC 8785 implementation.
    """
    doc = {"\uff01": 1, "\U0001f600": 2}  # U+FF01 FULLWIDTH EXCLAMATION MARK
    assert next(iter(json.loads(canonicalize(doc)))) == "\U0001f600"
    assert sorted(doc)[0] == "\uff01"  # Python's order, deliberately different


def test_arrays_preserve_order() -> None:
    assert canonicalize([3, 1, 2]) == "[3,1,2]"


def test_nested_structures() -> None:
    assert canonicalize({"a": [{"b": 1}, []], "c": {}}) == '{"a":[{"b":1},[]],"c":{}}'


# --------------------------------------------------------------------------- stability


def test_recanonicalize_is_independent_of_formatting() -> None:
    doc = {"b": [1, 2], "a": "x"}
    pretty = json.dumps(doc, indent=4)
    compact = json.dumps(doc, separators=(",", ":"))
    assert recanonicalize(pretty) == recanonicalize(compact) == canonical_bytes(doc)


def test_recanonicalize_accepts_bytes() -> None:
    assert recanonicalize(b'{"a":1}') == canonical_bytes({"a": 1})


def test_canonical_form_is_idempotent() -> None:
    doc = {"z": 1.5, "a": [True, None, "ü"]}
    once = canonical_bytes(doc)
    assert recanonicalize(once) == once


def test_exponent_spelling_is_normalised() -> None:
    assert canonicalize(1e-5) == "1e-5"
    assert canonicalize(1e22) == "1e+22"


# --------------------------------------------------------------------------- signing


def test_sign_and_verify_round_trip() -> None:
    key = generate_private_key()
    doc = {"a": 1, "b": ["x", None]}
    verify_statement(doc, sign_statement(doc, key), key.public_key())


def test_verification_is_insensitive_to_key_order() -> None:
    """The same document, differently ordered, must verify under one signature."""
    key = generate_private_key()
    signature = sign_statement({"a": 1, "b": 2}, key)
    verify_statement({"b": 2, "a": 1}, signature, key.public_key())


def test_any_change_breaks_verification() -> None:
    key = generate_private_key()
    doc = {"a": 1}
    signature = sign_statement(doc, key)
    with pytest.raises(SignatureInvalid):
        verify_statement({"a": 2}, signature, key.public_key())


def test_test_key_is_refused_by_default() -> None:
    with pytest.raises(SigningRefused, match="test key"):
        sign_statement({"a": 1}, fixture_private_key())


def test_test_key_signs_only_when_explicitly_allowed() -> None:
    key = fixture_private_key()
    signature = sign_statement({"a": 1}, key, allow_test_key=True)
    verify_statement({"a": 1}, signature, key.public_key())


def test_is_test_key_recognises_both_halves() -> None:
    key = fixture_private_key()
    assert is_test_key(key) and is_test_key(key.public_key())
    assert not is_test_key(generate_private_key())


def test_key_round_trips_through_disk(tmp_path: Path) -> None:
    key = generate_private_key()
    priv, pub = tmp_path / "k.ed25519", tmp_path / "pubkey.ed25519"
    write_private_key(key, priv)
    write_public_key(key.public_key(), pub)

    doc = {"a": 1}
    signature = sign_statement(doc, read_private_key(priv))
    verify_statement(doc, signature, read_public_key(pub))


def test_private_key_is_written_unreadable_to_others(tmp_path: Path) -> None:
    """0600 from creation — never world-readable, even briefly (NFR-14)."""
    path = tmp_path / "k.ed25519"
    write_private_key(generate_private_key(), path)
    assert path.stat().st_mode & 0o077 == 0


def test_reading_a_non_ed25519_key_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "junk.pem"
    path.write_bytes(b"-----BEGIN PRIVATE KEY-----\nnope\n-----END PRIVATE KEY-----\n")
    with pytest.raises(ValueError):
        read_private_key(path)


def test_float_precision_survives_signing() -> None:
    """One ULP apart must not share a signature."""
    key = generate_private_key()
    doc = {"x": 0.1}
    signature = sign_statement(doc, key)
    with pytest.raises(SignatureInvalid):
        verify_statement({"x": math.nextafter(0.1, math.inf)}, signature, key.public_key())
