"""FR-B-03's instrument, tested against a fake index.

This module decides whether the project's headline security claim is true, so
the parts that could silently produce a wrong number are exercised directly:
per-request attribution, and the refusal to attribute when it cannot.
"""

from __future__ import annotations

import httpx
import pytest

from barrier.attack.demo_frb03 import DemoError, run_demo

_METRICS = "http://epp/metrics"
_GATEWAY = "http://gw"


class FakeCluster:
    """A prefix index with a knob for how much each request matches.

    `lookups_per_request` exists so the attribution guard can be tested: at
    anything other than 1 the demo must refuse rather than divide.
    """

    def __init__(self, *, leaks: bool, lookups_per_request: int = 1) -> None:
        self.leaks = leaks
        self.lookups_per_request = lookups_per_request
        self.count = 0.0
        self.total = 0.0
        self.seen: set[str] = set()
        self.status = 200

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/metrics":
            body = (
                f'inference_extension_prefix_indexer_hit_ratio_bucket{{le="0"}} 0\n'
                f"inference_extension_prefix_indexer_hit_ratio_sum {self.total}\n"
                f"inference_extension_prefix_indexer_hit_ratio_count {self.count}\n"
            )
            return httpx.Response(200, text=body)

        if self.status != 200:
            return httpx.Response(self.status, text="nope")

        import json as _json

        prompt = _json.loads(request.content)["prompt"]
        key = request.headers["authorization"]
        # A hit means the text is in the index AND the namespace is shared.
        namespace = "shared" if self.leaks else key
        marker = f"{namespace}::{prompt}"
        ratio = 0.95 if marker in self.seen else 0.01
        self.seen.add(marker)
        self.count += self.lookups_per_request
        self.total += ratio
        return httpx.Response(200, json={"id": "cmpl-1", "choices": []})


def _client(cluster: FakeCluster) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(cluster.handler))


def test_a_leaking_cluster_clears_the_pre_registered_bar() -> None:
    """The attack half. Tenant A reaches what tenant B planted."""
    cluster = FakeCluster(leaks=True)
    with _client(cluster) as http:
        result = run_demo(
            gateway=_GATEWAY,
            metrics_url=_METRICS,
            key_a="a",
            key_b="b",
            profile="default",
            trials=20,
            client=http,
        )
    assert result.verdict["auc"] == 1.0
    assert result.verdict["attack_succeeds"] is True
    assert result.verdict["at_chance"] is False


def test_a_partitioned_cluster_sits_at_chance() -> None:
    """The mitigation half. Same schedule, salted namespaces, nothing to reach."""
    cluster = FakeCluster(leaks=False)
    with _client(cluster) as http:
        result = run_demo(
            gateway=_GATEWAY,
            metrics_url=_METRICS,
            key_a="a",
            key_b="b",
            profile="hardened",
            trials=20,
            client=http,
        )
    assert result.verdict["attack_succeeds"] is False
    assert result.verdict["at_chance"] is True


def test_attribution_is_refused_when_the_index_moves_by_more_than_one() -> None:
    """The guard that keeps a wrong number out of the writeup.

    If a request maps to more than one index lookup, the sum-delta is not that
    request's match ratio and every number downstream is fiction. Run #13 taught
    that an aggregate can look perfectly reasonable and mean nothing.
    """
    cluster = FakeCluster(leaks=True, lookups_per_request=2)
    with _client(cluster) as http, pytest.raises(DemoError, match="recorded 2 lookups"):
        run_demo(
            gateway=_GATEWAY,
            metrics_url=_METRICS,
            key_a="a",
            key_b="b",
            profile="default",
            trials=2,
            client=http,
        )


def test_a_non_200_from_the_gateway_is_not_silently_measured() -> None:
    """A 401 from the hardened proxy must not be recorded as 'no match found'.

    Otherwise a broken credential would present as a perfect mitigation.
    """
    cluster = FakeCluster(leaks=True)
    cluster.status = 401
    with _client(cluster) as http, pytest.raises(DemoError, match="answered 401"):
        run_demo(
            gateway=_GATEWAY,
            metrics_url=_METRICS,
            key_a="a",
            key_b="b",
            profile="hardened",
            trials=1,
            client=http,
        )


def test_an_empty_index_is_refused_rather_than_treated_as_no_leak() -> None:
    cluster = FakeCluster(leaks=True)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/metrics":
            return httpx.Response(200, text="# no such metric family\n")
        return cluster.handler(request)

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as http,
        pytest.raises(DemoError, match="no index to attribute"),
    ):
        run_demo(
            gateway=_GATEWAY,
            metrics_url=_METRICS,
            key_a="a",
            key_b="b",
            profile="hardened",
            trials=1,
            client=http,
        )
