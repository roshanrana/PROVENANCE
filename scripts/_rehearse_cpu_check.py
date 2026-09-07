"""The assertions the CPU rehearsal actually makes.

Called by ``scripts/rehearse-cpu.sh``. Kept separate so the checks are readable
and testable rather than buried in shell.

This is a **plumbing** check, not a measurement. It answers one question:

    when the harness talks to a real vLLM instead of our own stub,
    does anything disagree?

Everything it checks is something the stub cannot falsify, because the stub was
written by the same people as the client. Each finding is reported rather than
raised where possible, so one rehearsal surfaces every problem instead of
stopping at the first — the point is to spend the GPU session on measurement,
not on a queue of integration bugs discovered one per run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import httpx

from attest.harness.engine import EngineClient, EngineError, logprobs_digest
from attest.harness.vllm import VllmConfig, read_resolved_state
from attest.receipt.schema import SamplingParams

#: Top-level keys /server_info is expected to return. Their absence is not fatal
#: — the code degrades honestly — but it IS the difference between a receipt
#: that confirms the engine's configuration and one that merely repeats our own
#: request back to us.
SERVER_INFO_KEYS = ("vllm_config", "vllm_env")

#: Nested paths the receipt's engine block is actually built from. Written as
#: (label, getter) because /server_info nests them, and the flat lookup this
#: file originally used was itself the bug the rehearsal exists to catch.
NESTED_READBACKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("vllm_env.VLLM_BATCH_INVARIANT", ("vllm_env", "VLLM_BATCH_INVARIANT")),
    ("vllm_env.VLLM_ATTENTION_BACKEND", ("vllm_env", "VLLM_ATTENTION_BACKEND")),
    (
        "vllm_config.cache_config.enable_prefix_caching",
        ("vllm_config", "cache_config", "enable_prefix_caching"),
    ),
    (
        "vllm_config.parallel_config.tensor_parallel_size",
        ("vllm_config", "parallel_config", "tensor_parallel_size"),
    ),
)


def _dig(doc: Any, path: tuple[str, ...]) -> Any:
    for key in path:
        if not isinstance(doc, dict) or key not in doc:
            return None
        doc = doc[key]
    return doc


def _check(findings: list[dict[str, Any]], name: str, ok: bool, detail: str) -> bool:
    findings.append({"check": name, "ok": ok, "detail": detail})
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    findings: list[dict[str, Any]] = []
    sampling = SamplingParams(seed=0, temperature=0.0, top_p=1.0, max_tokens=16)

    # --- 1. the wire format -------------------------------------------------
    print("wire format")
    completion = None
    try:
        with EngineClient(args.base_url) as client:
            completion = client.complete("The capital of France is", sampling, model=args.model)
        _check(
            findings,
            "engine_client.complete",
            True,
            f"{len(completion.token_ids)} token ids, {len(completion.logprobs)} logprobs",
        )
    except EngineError as exc:
        _check(findings, "engine_client.complete", False, str(exc))

    if completion is not None:
        _check(
            findings,
            "token_ids_present",
            bool(completion.token_ids),
            "return_token_ids was honoured"
            if completion.token_ids
            else "engine returned no token ids",
        )
        _check(
            findings,
            "logprobs_align_with_tokens",
            len(completion.logprobs) == len(completion.token_ids),
            f"{len(completion.logprobs)} logprobs vs {len(completion.token_ids)} tokens",
        )
        _check(
            findings,
            "logprobs_digest_is_computable",
            len(logprobs_digest(completion.logprobs)) == 64,
            "sha256 over the packed doubles",
        )

    # --- 2. the readback (D-08) --------------------------------------------
    print("configuration readback (D-08)")
    config = VllmConfig(model=args.model, batch_invariant=False, enable_prefix_caching=False)
    try:
        state = read_resolved_state(args.base_url, config)
        _check(
            findings,
            "read_resolved_state",
            True,
            f"engine={state.engine} version={state.engine_version} "
            f"backend={state.attention_backend}",
        )
        exposed = state.resolved_config
        note = str(exposed.get("note", ""))
        _check(
            findings,
            "server_info_exposed",
            "exposed no server_info" not in note,
            note or f"{len(exposed)} fields",
        )
        for key in SERVER_INFO_KEYS:
            _check(
                findings,
                f"server_info_key:{key}",
                key in exposed,
                "present" if key in exposed else "ABSENT — /server_info shape has changed",
            )
        for label, path in NESTED_READBACKS:
            value = _dig(exposed, path)
            _check(
                findings,
                f"readback:{label}",
                value is not None,
                f"= {value!r}"
                if value is not None
                else "ABSENT — receipt would record intent, not reality",
            )
    except EngineError as exc:
        _check(findings, "read_resolved_state", False, str(exc))

    # --- 3. determinism is absent, and must be recorded as absent -----------
    #
    # The rehearsal must not accidentally look like a successful determinism
    # run. This asserts the negative explicitly, so a reader of the findings
    # file cannot mistake it for evidence.
    print("determinism (expected absent on CPU)")
    try:
        info = httpx.get(
            f"{args.base_url}/server_info", params={"config_format": "json"}, timeout=30
        ).json()
    except (httpx.HTTPError, ValueError):
        info = {}
    claims_invariance = str(
        _dig(info, ("vllm_env", "VLLM_BATCH_INVARIANT")) or ""
    ).strip().lower() in ("true", "1")
    _check(
        findings,
        "no_false_determinism_claim",
        not claims_invariance,
        "engine does not claim batch invariance, as expected on CPU"
        if not claims_invariance
        else "engine CLAIMS invariance on CPU — investigate before trusting anything here",
    )

    # --- 4. repeatability at fixed batch shape ------------------------------
    #
    # NOT a determinism result. Serial, single-request, no batching, no
    # invariant kernels. If it differs, something is wrong with the harness or
    # with sampling; if it matches, that says nothing about batch invariance and
    # the writeup must not cite it.
    print("serial repeatability (NOT a determinism result)")
    try:
        with EngineClient(args.base_url) as client:
            first = client.complete("The capital of France is", sampling, model=args.model)
            second = client.complete("The capital of France is", sampling, model=args.model)
        identical = logprobs_digest(first.logprobs) == logprobs_digest(second.logprobs)
        _check(
            findings,
            "serial_repeatability",
            identical,
            "two serial identical requests produced identical logprobs"
            if identical
            else "two serial identical requests DIFFERED — harness or sampling issue",
        )
    except EngineError as exc:
        _check(findings, "serial_repeatability", False, str(exc))

    failed = [f for f in findings if not f["ok"]]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "base_url": args.base_url,
                "model": args.model,
                "purpose": "plumbing rehearsal against a real vLLM on CPU; measures nothing",
                "determinism_measured": False,
                "findings": findings,
                "failed": len(failed),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print()
    if failed:
        print(f"{len(failed)} check(s) failed — fix these before spending GPU minutes:")
        for f in failed:
            print(f"  - {f['check']}: {f['detail']}")
        return 1
    print("all checks passed. The harness talks to a real engine correctly.")
    print("This says nothing about determinism, which CPU cannot exercise.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
