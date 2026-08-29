"""Self-tests for the stub engine.

A test double that is silently wrong is worse than none: every ATTEST test would
inherit its error while appearing to pass.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx

from tests.support.stub_engine import StubConfig, stub_engine


def _complete(url: str, prompt: str = "hello", **extra: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "prompt": prompt,
        "seed": 0,
        "temperature": 0.0,
        "max_tokens": 8,
        **extra,
    }
    body: dict[str, Any] = httpx.post(f"{url}/v1/completions", json=payload, timeout=10).json()
    return body


def test_determinism_mode_none_is_byte_identical() -> None:
    with stub_engine(StubConfig(divergence_mode="none")) as stub:
        a = _complete(stub.url)["choices"][0]
        b = _complete(stub.url)["choices"][0]
    assert a["token_ids"] == b["token_ids"]
    assert a["logprobs"] == b["logprobs"]


def test_batch_dependent_mode_diverges_under_concurrency() -> None:
    """Identical requests, different concurrency, different output — the phenomenon."""
    with stub_engine(StubConfig(divergence_mode="batch_dependent")) as stub:
        serial = _complete(stub.url)["choices"][0]["token_ids"]

        with ThreadPoolExecutor(max_workers=12) as pool:
            results = [f.result() for f in [pool.submit(_complete, stub.url) for _ in range(12)]]

        assert stub.state.peak_inflight > 1, "test did not actually achieve concurrency"
        concurrent_variants = {tuple(r["choices"][0]["token_ids"]) for r in results}

    assert tuple(serial) not in concurrent_variants or len(concurrent_variants) > 1


def test_batch_dependent_mode_is_reproducible_for_a_fixed_bucket() -> None:
    """Divergence is deterministic given the bucket — not random noise."""
    with stub_engine(StubConfig(divergence_mode="batch_dependent")) as stub:
        a = _complete(stub.url)["choices"][0]["token_ids"]
        b = _complete(stub.url)["choices"][0]["token_ids"]
    assert a == b


def test_random_mode_differs_every_call() -> None:
    with stub_engine(StubConfig(divergence_mode="random")) as stub:
        seen = {tuple(_complete(stub.url)["choices"][0]["token_ids"]) for _ in range(4)}
    assert len(seen) > 1


def test_different_seeds_give_different_output() -> None:
    with stub_engine() as stub:
        a = _complete(stub.url, seed=0)["choices"][0]["token_ids"]
        b = _complete(stub.url, seed=1)["choices"][0]["token_ids"]
    assert a != b


def test_resolved_config_differs_from_the_request() -> None:
    """D-08 conformance must be testable: intent and reality must not coincide."""
    with stub_engine() as stub:
        resolved = httpx.get(f"{stub.url}/_stub/resolved_config", timeout=10).json()
    assert resolved["resolved_config"]["cudagraph_mode"] == "PIECEWISE"
    assert resolved["attention_backend"] == "FLASH_ATTN"
    assert resolved["tensor_parallel_size"] == 1


def test_version_and_models_endpoints() -> None:
    with stub_engine() as stub:
        version = httpx.get(f"{stub.url}/version", timeout=10).json()
        models = httpx.get(f"{stub.url}/v1/models", timeout=10).json()
    assert version["version"].endswith("-stub")
    assert models["data"][0]["id"] == "Qwen/Qwen2.5-0.5B-Instruct"


def test_cache_salt_is_echoed_for_barrier_tests() -> None:
    with stub_engine() as stub:
        body = _complete(stub.url, cache_salt="tenant-a")
    assert body["_stub"]["cache_salt"] == "tenant-a"


def test_unknown_path_is_404() -> None:
    with stub_engine() as stub:
        assert httpx.get(f"{stub.url}/nope", timeout=10).status_code == 404


def test_two_instances_do_not_collide_on_a_port() -> None:
    with stub_engine() as first, stub_engine() as second:
        assert first.url != second.url
        assert _complete(first.url) and _complete(second.url)


def test_max_tokens_is_honoured() -> None:
    with stub_engine() as stub:
        assert len(_complete(stub.url, max_tokens=3)["choices"][0]["token_ids"]) == 3
