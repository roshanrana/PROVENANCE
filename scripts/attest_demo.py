#!/usr/bin/env python
"""``make attest-demo`` — the M0 walking skeleton, end to end, with no GPU.

Starts the stub engine, drives the production harness against it, then verifies
the receipt the harness produced by shelling out to the real ``attest verify``
CLI. Verifying through the CLI rather than in-process is the point: the demo
proves the shipped exit-code contract, not a convenient internal shortcut.

Lives in ``scripts/`` rather than in the ``attest`` package because it imports
the stub from ``tests/support``, and production code must never import tests.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from attest.harness.skeleton import run_skeleton
from attest.receipt import cli
from tests.support.stub_engine import StubConfig, stub_engine


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=REPO_ROOT / "bench" / "results")
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep the run directory (default: it is a demo, so it is removed).",
    )
    args = parser.parse_args()

    with stub_engine(StubConfig(divergence_mode="none")) as stub:
        result = run_skeleton(
            engine_url=stub.url,
            results_root=args.results_root,
            use_test_key=True,
            command="make attest-demo",
        )

    print(f"run_id      : {result.run_id}")
    print(f"run_dir     : {result.run_dir}")
    print(f"cells       : done={result.cells_done} failed={result.cells_failed}")

    # --- artefacts the pipeline must have produced -------------------------
    expected = [
        result.run_dir / "manifest.json",
        result.run_dir / "cells.jsonl",
        result.run_dir / "c0001.jsonl",
        result.run_dir / "receipts" / "receipt.json",
        result.run_dir / "receipts" / "receipt.sig",
        result.run_dir / "receipts" / "pubkey.ed25519",
    ]
    missing = [p for p in expected if not p.exists()]
    if missing:
        print("FAIL: pipeline did not produce:", *[f"  {p}" for p in missing], sep="\n")
        return 1
    print(f"artefacts   : {len(expected)} present")

    # --- verify through the shipped CLI ------------------------------------
    receipt = result.run_dir / "receipts" / "receipt.json"
    code = cli.main(["verify", str(receipt), "--allow-test-key"])
    if code != cli.EXIT_OK:
        print(f"FAIL: attest verify exited {code}, expected {cli.EXIT_OK}")
        return 1

    # A demo that only proves the happy path proves very little. Tamper with the
    # receipt and require the exact contracted exit code.
    tampered = result.run_dir / "receipts" / "tampered.json"
    doc = json.loads(receipt.read_text())
    doc["predicate"]["output"]["token_ids"] = [1, 2, 3]
    tampered.write_text(json.dumps(doc))
    (result.run_dir / "receipts" / "tampered.sig").write_bytes(
        (result.run_dir / "receipts" / "receipt.sig").read_bytes()
    )
    code = cli.main(["verify", str(tampered), "--allow-test-key"])
    if code != cli.EXIT_DIGEST_MISMATCH:
        print(f"FAIL: tampered receipt exited {code}, expected {cli.EXIT_DIGEST_MISMATCH}")
        return 1
    tampered.unlink()
    (result.run_dir / "receipts" / "tampered.sig").unlink()

    print("verify      : OK (valid=0, tampered=3)")

    if not args.keep:
        import shutil

        shutil.rmtree(result.run_dir, ignore_errors=True)
        (REPO_ROOT / ".signing-key.ed25519").unlink(missing_ok=True)
        print("cleanup     : demo run directory removed (pass --keep to retain)")

    print("\nM0 walking skeleton: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
