"""M0 — the walking skeleton.

One inference travelling the whole pipeline: matrix cell → ledger → engine →
raw JSONL → signed receipt → verified receipt → manifest, written into an
immutable ``bench/results/<run-id>/`` directory.

It runs against whatever engine URL it is given, so in CI that is the stub and no
GPU is involved. The point is not the inference; it is that every seam in the
real architecture is exercised while the codebase is still small enough to change
cheaply.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from attest.harness.engine import EngineClient
from attest.harness.ledger import Ledger
from attest.receipt.canonical import canonical_bytes
from attest.receipt.schema import ModelIdentity, Receipt, RunRef, SamplingParams
from attest.receipt.sign import (
    generate_private_key,
    is_test_key,
    sign_statement,
    test_private_key,
    write_private_key,
    write_public_key,
)
from common.runid import Manifest, iso, utc_now

DEFAULT_PROMPT = "Summarise the counterparty exposure in one sentence."
DEFAULT_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"


@dataclass(frozen=True)
class SkeletonResult:
    run_dir: Path
    run_id: str
    receipt_path: Path
    cells_done: int
    cells_failed: int


def run_skeleton(
    *,
    engine_url: str,
    results_root: Path,
    prompt: str = DEFAULT_PROMPT,
    model: str = DEFAULT_MODEL,
    use_test_key: bool = False,
    command: str = "make attest-demo",
    git: tuple[str, bool] | None = None,
) -> SkeletonResult:
    manifest = Manifest.start("attest", command=command, git=git)
    run_dir = results_root / manifest.run_id
    receipts_dir = run_dir / "receipts"
    run_dir.mkdir(parents=True, exist_ok=True)

    ledger = Ledger.in_dir(run_dir)
    cell_id = "c0001"
    ledger.seed([{"cell_id": cell_id, "params": {"prompt": prompt, "invariant": False}}])

    sampling = SamplingParams(seed=0, temperature=0.0, top_p=1.0, max_tokens=16)
    raw_path = run_dir / f"{cell_id}.jsonl"

    cells_done = cells_failed = 0
    try:
        ledger.mark_running(cell_id)
        with EngineClient(engine_url) as engine:
            engine_state = engine.resolved_state()
            completion = engine.complete(prompt, sampling, model=model)

        with open(raw_path, "a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "cell_id": cell_id,
                        "prompt": prompt,
                        "token_ids": completion.token_ids,
                        "text": completion.text,
                        "logprobs": completion.logprobs,
                        "ts_utc": iso(utc_now()),
                    },
                    sort_keys=True,
                )
                + "\n"
            )

        receipt = Receipt(
            # M0 records identity as `unresolved`: the skeleton must run with no
            # network (NFR-08), and an honest "not checked" beats a fabricated
            # hash. T-019 resolves it for real.
            model=ModelIdentity(
                repo_id=model,
                commit_sha="",
                weights_file="model.safetensors",
                weights_lfs_sha256="",
                resolution="unresolved",
            ),
            engine=engine_state,
            sampling=sampling,
            output=completion.to_output_record(),
            run=RunRef(run_id=manifest.run_id, cell_id=cell_id, timestamp_utc=iso(utc_now())),
        )
        _emit_receipt(receipt, receipts_dir, use_test_key=use_test_key)

        ledger.mark_done(cell_id, str(raw_path.relative_to(run_dir)))
        cells_done = 1
    except Exception as exc:
        ledger.mark_failed(cell_id, f"{type(exc).__name__}: {exc}")
        cells_failed = 1
        _write_manifest(manifest, run_dir, 1, cells_done, cells_failed)
        raise
    finally:
        if cells_failed == 0:
            _write_manifest(manifest, run_dir, 1, cells_done, cells_failed)

    return SkeletonResult(
        run_dir=run_dir,
        run_id=manifest.run_id,
        receipt_path=receipts_dir / "receipt.json",
        cells_done=cells_done,
        cells_failed=cells_failed,
    )


def _emit_receipt(receipt: Receipt, receipts_dir: Path, *, use_test_key: bool) -> Path:
    receipts_dir.mkdir(parents=True, exist_ok=True)
    statement = receipt.to_statement()

    key = test_private_key() if use_test_key else generate_private_key()
    signature = sign_statement(statement, key, allow_test_key=is_test_key(key))

    receipt_path = receipts_dir / "receipt.json"
    receipt_path.write_bytes(canonical_bytes(statement))
    (receipts_dir / "receipt.sig").write_bytes(signature)
    write_public_key(key.public_key(), receipts_dir / "pubkey.ed25519")
    if not use_test_key:
        # Private key stays out of the results tree and out of git (NFR-14).
        write_private_key(key, receipts_dir.parent.parent / ".signing-key.ed25519")
    return receipt_path


def _write_manifest(manifest: Manifest, run_dir: Path, total: int, done: int, failed: int) -> None:
    manifest.finalize(cells_total=total, cells_done=done, cells_failed=failed).write(
        run_dir / "manifest.json"
    )


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run the M0 walking skeleton.")
    parser.add_argument("--engine-url", required=True)
    parser.add_argument("--results-root", type=Path, default=Path("bench/results"))
    parser.add_argument(
        "--test-key",
        action="store_true",
        help="Sign with the published fixture key (CI demo runs).",
    )
    args = parser.parse_args(argv)

    result = run_skeleton(
        engine_url=args.engine_url,
        results_root=args.results_root,
        use_test_key=args.test_key,
    )
    summary: dict[str, Any] = {
        "run_id": result.run_id,
        "run_dir": str(result.run_dir),
        "receipt": str(result.receipt_path),
        "cells_done": result.cells_done,
        "cells_failed": result.cells_failed,
    }
    print(json.dumps(summary, sort_keys=True))
    return 0 if result.cells_failed == 0 else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
