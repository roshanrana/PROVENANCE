"""ed25519 signing and verification for attestation receipts.

ADR-005: offline-verifiable by design. FR-A-06 requires verification with no
network and no running engine, and D-13 bars account requirements from the
reproduction path — which is what rules out keyless signing today.

Key custody (HLD §8.2): the private key is generated per run and never committed;
the public key is committed next to the receipts so verification needs nothing
else. CI signs fixtures with a fixed, clearly-labelled **test key**, and this
module refuses to sign a non-test receipt with it.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from attest.receipt.canonical import canonical_bytes

#: Seed for the fixture key. Deterministic, published, and worthless — which is
#: the point: anything it signs must be identifiable as a fixture.
TEST_KEY_SEED = b"PROVENANCE-TEST-KEY-DO-NOT-TRUST"  # exactly 32 bytes
TEST_KEY_LABEL = "provenance-test-key-do-not-trust"


class SigningRefused(RuntimeError):
    """Refusal to produce a signature that would misrepresent its own trust level."""


class SignatureInvalid(Exception):
    """The signature does not verify against the public key and document."""


def test_private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(TEST_KEY_SEED)


def is_test_key(key: Ed25519PrivateKey | Ed25519PublicKey) -> bool:
    reference = test_private_key().public_key()
    public = key.public_key() if isinstance(key, Ed25519PrivateKey) else key
    return public_bytes(public) == public_bytes(reference)


def public_bytes(key: Ed25519PublicKey) -> bytes:
    return key.public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )


def generate_private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def write_private_key(key: Ed25519PrivateKey, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    # Written 0600 from the start — never world-readable, even briefly.
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)


def read_private_key(path: Path) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError(f"not an ed25519 private key: {path}")
    return key


def write_public_key(key: Ed25519PublicKey, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )


def read_public_key(path: Path) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(path.read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError(f"not an ed25519 public key: {path}")
    return key


@dataclass(frozen=True)
class SignedStatement:
    statement: Mapping[str, Any]
    signature: bytes


def sign_statement(
    statement: Mapping[str, Any],
    key: Ed25519PrivateKey,
    *,
    allow_test_key: bool = False,
) -> bytes:
    """Sign the canonical bytes of *statement*.

    Refuses the fixture key unless the caller explicitly says it is producing a
    fixture. A receipt signed by a published key while presenting itself as
    genuine evidence is worse than an unsigned one.
    """
    if is_test_key(key) and not allow_test_key:
        raise SigningRefused(
            f"refusing to sign with the published test key ({TEST_KEY_LABEL}); "
            "pass allow_test_key=True only when generating fixtures"
        )
    return key.sign(canonical_bytes(statement))


def verify_statement(statement: Mapping[str, Any], signature: bytes, key: Ed25519PublicKey) -> None:
    """Raise :class:`SignatureInvalid` unless *signature* covers *statement*.

    The canonical bytes are recomputed from the parsed document, so this is
    independent of how the file on disk happened to be formatted.
    """
    try:
        key.verify(signature, canonical_bytes(statement))
    except InvalidSignature as exc:
        raise SignatureInvalid("ed25519 signature does not verify") from exc
