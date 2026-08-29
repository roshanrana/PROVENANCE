"""``attest`` — receipt verification.

The exit codes are a contract (LLD §5). Collapsing *tampered*, *malformed*, and
*unreachable* into a single failure is a defect, not a simplification: a model
validator has to be able to tell "someone edited this" from "the file is corrupt"
from "I have no network right now". Only the last of those is retryable, and only
the last is allowed to degrade (HLD §8.4).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from attest.receipt.schema import Receipt, ReceiptSchemaError, SubjectDigestMismatch
from attest.receipt.sign import (
    SignatureInvalid,
    is_test_key,
    read_public_key,
    verify_statement,
)

EXIT_OK = 0
EXIT_SIGNATURE_INVALID = 2
EXIT_DIGEST_MISMATCH = 3
EXIT_MALFORMED = 4
EXIT_HUB_UNREACHABLE = 5
EXIT_IDENTITY_DIVERGENT = 6
EXIT_TEST_KEY = 7


@dataclass(frozen=True)
class Paths:
    receipt: Path
    signature: Path
    public_key: Path

    @classmethod
    def beside(cls, receipt: Path) -> Paths:
        """Sibling layout: ``receipt.json`` + ``receipt.sig`` + ``pubkey.ed25519``."""
        return cls(
            receipt=receipt,
            signature=receipt.with_suffix(".sig"),
            public_key=receipt.parent / "pubkey.ed25519",
        )


def _verify(paths: Paths, *, allow_test_key: bool, online: bool, out: TextIO) -> int:
    # --- parse -------------------------------------------------------------
    try:
        raw = paths.receipt.read_text(encoding="utf-8")
        document = json.loads(raw)
    except FileNotFoundError:
        print(f"MALFORMED: no such receipt: {paths.receipt}", file=out)
        return EXIT_MALFORMED
    except json.JSONDecodeError as exc:
        print(f"MALFORMED: not valid JSON: {exc}", file=out)
        return EXIT_MALFORMED

    try:
        receipt = Receipt.from_statement(document)
    except SubjectDigestMismatch as exc:
        # Edited, not corrupt. Different code on purpose.
        print(f"DIGEST MISMATCH: output ({exc})", file=out)
        return EXIT_DIGEST_MISMATCH
    except ReceiptSchemaError as exc:
        print(f"MALFORMED: {exc}", file=out)
        return EXIT_MALFORMED

    # --- signature ---------------------------------------------------------
    try:
        signature = paths.signature.read_bytes()
        public_key = read_public_key(paths.public_key)
    except FileNotFoundError as exc:
        print(f"MALFORMED: {exc}", file=out)
        return EXIT_MALFORMED
    except ValueError as exc:
        print(f"MALFORMED: unreadable public key: {exc}", file=out)
        return EXIT_MALFORMED

    if is_test_key(public_key) and not allow_test_key:
        print(
            "REFUSING: test key — this receipt is signed by the published fixture key "
            "and is not evidence of anything. Re-run with --allow-test-key if you are "
            "verifying a fixture on purpose.",
            file=out,
        )
        return EXIT_TEST_KEY

    try:
        verify_statement(document, signature, public_key)
    except SignatureInvalid:
        print("SIGNATURE INVALID", file=out)
        return EXIT_SIGNATURE_INVALID

    # --- optional Hub cross-check -----------------------------------------
    if online:
        from attest.receipt.provenance import HubUnreachable, resolve_model_identity

        try:
            live = resolve_model_identity(receipt.model.repo_id)
        except HubUnreachable as exc:
            print(
                f"HUB UNREACHABLE — offline verification passed ({exc}). "
                "Model identity was not cross-checked.",
                file=out,
            )
            return EXIT_HUB_UNREACHABLE

        for field, bound, observed in (
            ("commit_sha", receipt.model.commit_sha, live.commit_sha),
            ("weights.lfs_sha256", receipt.model.weights_lfs_sha256, live.weights_lfs_sha256),
        ):
            if bound != observed:
                print(
                    f"IDENTITY DIVERGENT: {field} local={bound!r} hub={observed!r}",
                    file=out,
                )
                return EXIT_IDENTITY_DIVERGENT

    print(f"OK {receipt.run.run_id}/{receipt.run.cell_id}", file=out)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="attest", description="Attestation receipt tooling.")
    sub = parser.add_subparsers(dest="command", required=True)

    verify = sub.add_parser("verify", help="Verify a receipt. Offline by default.")
    verify.add_argument("receipt", type=Path)
    verify.add_argument(
        "--online",
        action="store_true",
        help="Additionally resolve model identity against the Hugging Face Hub.",
    )
    verify.add_argument(
        "--allow-test-key",
        action="store_true",
        help="Accept the published fixture key. Only for verifying fixtures.",
    )
    verify.add_argument("--signature", type=Path, default=None)
    verify.add_argument("--public-key", type=Path, default=None)
    return parser


def main(argv: Sequence[str] | None = None, *, out: TextIO | None = None) -> int:
    args = build_parser().parse_args(argv)
    stream = out if out is not None else sys.stdout

    if args.command == "verify":
        paths = Paths.beside(args.receipt)
        if args.signature is not None:
            paths = Paths(paths.receipt, args.signature, paths.public_key)
        if args.public_key is not None:
            paths = Paths(paths.receipt, paths.signature, args.public_key)
        return _verify(paths, allow_test_key=args.allow_test_key, online=args.online, out=stream)

    raise AssertionError(f"unhandled command: {args.command!r}")  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
