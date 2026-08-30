"""Self-tests for the stub engine.

A test double that is silently wrong is worse than none: every ATTEST test would
inherit its error while appearing to pass.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx

from tests.support.stub_engine import (
    StubConfig,
    _bucket_for,
    _tokens_for,
    stub_engine,
)


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


def test_bucket_boundaries_model_kernel_batch_shapes() -> None:
    """The divergence *logic*, tested deterministically — no threads involved.

    Buckets stand in for the batch shapes at which real kernels switch reduction
    strategy. Testing this directly is what makes the HTTP-level test below able
    to be loose without leaving the behaviour unverified.
    """
    assert [_bucket_for(n) for n in (1, 2, 4, 5, 8, 9, 64)] == [0, 1, 1, 2, 2, 3, 3]


def test_identical_requests_diverge_across_batch_shapes() -> None:
    """Same prompt, same seed, different batch shape, different tokens.

    This is the phenomenon ATTEST exists to measure, and at this level it is a
    pure function — so it is checked exactly rather than by racing threads.
    """
    variants = {tuple(_tokens_for("p", 0, bucket, 8)) for bucket in range(4)}
    assert len(variants) == 4


def test_concurrency_reaches_non_serial_buckets_over_http() -> None:
    """Wiring check: under real load the server does reach a larger batch shape.

    Deliberately a weak assertion. An earlier version of this test pinned an
    exact bucket and failed about one run in four, because HTTP connection
    lifecycle decides how many requests genuinely overlap. The exact behaviour is
    covered by the two pure-function tests above; this one only has to prove the
    path is wired up, so it asserts the least it can get away with.
    """
    config = StubConfig(
        divergence_mode="batch_dependent", latency_profile="fixed", fixed_latency_s=0.05
    )
    with stub_engine(config) as stub:
        with ThreadPoolExecutor(max_workers=12) as pool:
            futures = [pool.submit(_complete, stub.url) for _ in range(12)]
            results = [f.result() for f in futures]
        peak = stub.state.peak_inflight

    assert peak > 1, f"no overlap achieved at all (peak_inflight={peak})"
    assert {r["_stub"]["bucket"] for r in results} != {0}, "never left the serial bucket"


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
