"""The S-02 spike's discriminator logic.

The spike itself needs a cluster. What can be tested here — and what would
silently ruin the result if wrong — is *what counts as a discriminator*. A
detector that fires on a per-request id would declare an oracle viable when
nothing is leaking, and that false positive would send the whole of BARRIER down
the wrong path.
"""

from __future__ import annotations

from barrier.attack.spike_s02 import DECISION_RULE, Probe, SpikeResult, find_discriminators


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
        (_probe("h1", {"x-a": "1"}), _probe("m1", {"x-a": "2"})),
        (_probe("h2", {"x-b": "1"}), _probe("m2", {"x-b": "2"})),
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
