"""The S-02 spike's discriminator logic.

The spike itself needs a cluster. What can be tested here — and what would
silently ruin the result if wrong — is *what counts as a discriminator*. A
detector that fires on a per-request id would declare an oracle viable when
nothing is leaking, and that false positive would send the whole of BARRIER down
the wrong path.
"""

from __future__ import annotations

from barrier.attack.spike_s02 import (
    DECISION_RULE,
    Probe,
    SpikeResult,
    find_discriminators,
    measure_numeric_channels,
)


def _probe(label: str, headers: dict[str, str], body_keys: list[str] | None = None) -> Probe:
    return Probe(
        label=label,
        prompt="p",
        tenant="tenant-a",
        status=200,
        elapsed_ms=1.0,
        headers=headers,
        body_keys=body_keys or ["choices", "id", "model"],
        body_id="cmpl-1",
    )


def test_identical_responses_yield_no_discriminator() -> None:
    """The expected outcome given what source already tells us."""
    hit = _probe("hit", {"content-type": "application/json"})
    miss = _probe("miss", {"content-type": "application/json"})
    assert find_discriminators([(hit, miss)]) == []


def test_a_routing_header_is_detected() -> None:
    hit = _probe("hit", {"content-type": "application/json", "x-served-by": "pod-1"})
    miss = _probe("miss", {"content-type": "application/json", "x-served-by": "pod-2"})
    assert find_discriminators([(hit, miss)]) == ["header:x-served-by"]


def test_noisy_headers_do_not_count_as_signal() -> None:
    """A per-request id differs on every call and discriminates nothing.

    Counting it would declare an oracle viable when nothing leaks — a false
    positive that would send all of BARRIER down the wrong path.
    """
    hit = _probe("hit", {"date": "Mon", "x-request-id": "a", "content-length": "10"})
    miss = _probe("miss", {"date": "Tue", "x-request-id": "b", "content-length": "20"})
    assert find_discriminators([(hit, miss)]) == []


def test_a_header_present_on_only_one_side_counts() -> None:
    hit = _probe("hit", {"x-cache": "hit"})
    miss = _probe("miss", {})
    assert find_discriminators([(hit, miss)]) == ["header:x-cache"]


def test_body_shape_difference_counts() -> None:
    hit = _probe("hit", {}, body_keys=["choices", "id", "cached"])
    miss = _probe("miss", {}, body_keys=["choices", "id"])
    assert find_discriminators([(hit, miss)]) == ["body:key-set"]


def test_discriminators_across_many_pairs_are_unioned() -> None:
    pairs = [
        (_probe("h1", {"x-a": "pod-1"}), _probe("m1", {"x-a": "pod-2"})),
        (_probe("h2", {"x-b": "pod-1"}), _probe("m2", {"x-b": "pod-2"})),
    ]
    assert find_discriminators(pairs) == ["header:x-a", "header:x-b"]


# --------------------------------------------------------------------------- verdict


def test_verdict_reflects_no_signal() -> None:
    result = SpikeResult()
    assert "NO CLIENT-OBSERVABLE SIGNAL" in result.verdict()
    assert "rescope" in result.verdict()


def test_verdict_reflects_a_found_signal() -> None:
    result = SpikeResult(discriminators=["header:x-served-by"])
    assert "ORACLE VIABLE" in result.verdict()


def test_decision_rule_is_carried_into_the_evidence_file() -> None:
    """The rule travels with the result, so nobody has to trust that it predated it."""
    doc = SpikeResult().to_dict()
    assert doc["decision_rule"] == DECISION_RULE
    assert "fixed in advance" in doc["decision_rule"]


def test_probe_records_the_prompt_by_hash_not_verbatim() -> None:
    """MNPI-themed prompts are synthetic, but hashing keeps the habit right."""
    doc = _probe("hit", {}).to_dict()
    assert "prompt" not in doc
    assert len(doc["prompt_sha"]) == 16


# ------------------------------------------------------- run #6's false positive


def test_a_per_request_timer_is_not_a_discriminator() -> None:
    """CI run #6 returned ORACLE VIABLE on `x-envoy-upstream-service-time`.

    Envoy's upstream latency in milliseconds takes a fresh value on essentially
    every request, so it differs between *any* two probes. Counting it declared
    an oracle viable on a simulator that does not vary TTFT on cache hit versus
    miss at all — the wrong verdict on the one question BARRIER's shape turns on.
    """
    pairs = [
        (
            _probe(f"h{i}", {"x-envoy-upstream-service-time": str(210 + i)}),
            _probe(f"m{i}", {"x-envoy-upstream-service-time": str(310 + i)}),
        )
        for i in range(6)
    ]
    rejected: dict[str, str] = {}
    assert find_discriminators(pairs, rejected) == []
    assert "measurement" in rejected["header:x-envoy-upstream-service-time"]


def test_a_stable_routing_header_survives_the_same_number_of_pairs() -> None:
    """The control for the test above: a real signal repeats within its class."""
    pairs = [
        (_probe(f"h{i}", {"x-served-by": "pod-1"}), _probe(f"m{i}", {"x-served-by": "pod-2"}))
        for i in range(6)
    ]
    assert find_discriminators(pairs) == ["header:x-served-by"]


def test_a_field_that_differs_only_sometimes_is_rejected() -> None:
    """An oracle that classifies correctly two times in three is not an oracle."""
    pairs = [
        (_probe("h1", {"x-a": "pod-1"}), _probe("m1", {"x-a": "pod-2"})),
        (_probe("h2", {"x-a": "pod-1"}), _probe("m2", {"x-a": "pod-2"})),
        (_probe("h3", {"x-a": "pod-1"}), _probe("m3", {"x-a": "pod-1"})),
    ]
    rejected: dict[str, str] = {}
    assert find_discriminators(pairs, rejected) == []
    assert "2 of 3" in rejected["header:x-a"]


def test_a_numeric_header_that_separates_perfectly_is_still_not_categorical() -> None:
    """Run #7's lesson: duplicate millisecond values defeated the first fix.

    The first correction rejected a field whose values were *all distinct* on
    both sides. Millisecond integers collide by chance, so the same header
    survived a second run under the same wrong verdict. What makes it not a
    discriminator is not the pattern of its values but their *type*: it is a
    measurement, and measurements go to the pre-registered statistical rule.
    """
    pairs = [
        (
            _probe(f"h{i}", {"x-envoy-upstream-service-time": "205"}),
            _probe(f"m{i}", {"x-envoy-upstream-service-time": "216"}),
        )
        for i in range(6)
    ]
    rejected: dict[str, str] = {}
    assert find_discriminators(pairs, rejected) == []
    assert "pre-registered" in rejected["header:x-envoy-upstream-service-time"]


def test_a_value_seen_on_both_sides_cannot_classify() -> None:
    pairs = [
        (_probe("h1", {"x-served-by": "pod-1"}), _probe("m1", {"x-served-by": "pod-2"})),
        (_probe("h2", {"x-served-by": "pod-2"}), _probe("m2", {"x-served-by": "pod-1"})),
        (_probe("h3", {"x-served-by": "pod-1"}), _probe("m3", {"x-served-by": "pod-2"})),
    ]
    rejected: dict[str, str] = {}
    assert find_discriminators(pairs, rejected) == []
    assert "both sides" in rejected["header:x-served-by"]


def test_measurements_go_through_the_pre_registered_rule() -> None:
    """Latency is judged, not narrated. A separation this clean must clear the bar."""
    pairs = [
        (
            Probe("h", "p", "tenant-a", 200, 10.0 + i * 0.1, {}, ["choices"], "c"),
            Probe("m", "p", "tenant-a", 200, 90.0 + i * 0.1, {}, ["choices"], "c"),
        )
        for i in range(20)
    ]
    m = measure_numeric_channels(pairs)
    assert m["latency_ms"]["auc"] == 1.0
    assert m["latency_ms"]["attack_succeeds"] is True


def test_noise_does_not_clear_the_pre_registered_bar() -> None:
    """The simulator case: overlapping latencies must not be called an oracle."""
    pairs = [
        (
            Probe("h", "p", "tenant-a", 200, 200.0 + (i % 5), {}, ["choices"], "c"),
            Probe("m", "p", "tenant-a", 200, 200.0 + ((i + 2) % 5), {}, ["choices"], "c"),
        )
        for i in range(20)
    ]
    m = measure_numeric_channels(pairs)
    assert m["latency_ms"]["attack_succeeds"] is False
