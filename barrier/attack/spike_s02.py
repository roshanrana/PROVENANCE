"""S-02 — is there a client-observable routing signal on the simulator?

**This decides BARRIER's shape**, and the decision rule was written down in LLD §7
*before* any evidence existed, precisely so it could not be rationalised after we
saw the result. This script applies that rule as written.

What we already know from source, which is why the question is narrow:

* ``x-gateway-destination-endpoint-served`` is in ``OutputInjectionHeaders`` and is
  **stripped from the response** (`handlers/response.go:202`). The obvious signal
  is closed.
* ``--emit-endpoint-scores`` writes to Envoy dynamic metadata, not to the client.

So: does *anything* remain that an ordinary tenant caller can see?

The design that makes the answer trustworthy is the ground truth. We observe the
EPP's own routing decisions from inside the cluster **as well as** what the client
sees, so we can distinguish "no signal" from "signal we failed to look for". A
spike that only looked at the client side could not tell those apart.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

DECISION_RULE = (
    "LLD §7, fixed in advance: if step 1 (self-collision) yields no client-visible "
    "discriminator, FR-B-03 is rescoped to an operator-instrumented demonstration "
    "and the attacker-observable oracle moves entirely to FR-B-09 on real vLLM. "
    "That is a scope change recorded in decisions.md, not a failure, and it is "
    "published either way (NFR-17)."
)


@dataclass
class Probe:
    label: str
    prompt: str
    tenant: str
    status: int
    elapsed_ms: float
    headers: dict[str, str]
    body_keys: list[str]
    body_id: str | None
    served_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "tenant": self.tenant,
            "prompt_sha": _sha(self.prompt),
            "status": self.status,
            "elapsed_ms": self.elapsed_ms,
            "headers": self.headers,
            "body_keys": self.body_keys,
            "body_id": self.body_id,
            "served_by": self.served_by,
        }


def _sha(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode()).hexdigest()[:16]


@dataclass
class SpikeResult:
    probes: list[Probe] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    discriminators: list[str] = field(default_factory=list)
    # Every field that differed but was NOT counted, with the reason. Published
    # because "we looked and rejected it" and "we never looked" are different
    # claims, and only one of them is checkable.
    rejected: dict[str, str] = field(default_factory=dict)
    # Continuous channels — latency and every numeric header — each carrying the
    # full pre-registered verdict: AUC, its bootstrap interval, and p.
    measurements: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_rule": DECISION_RULE,
            "probes": [p.to_dict() for p in self.probes],
            "notes": self.notes,
            "client_observable_discriminators": self.discriminators,
            "rejected_candidates": self.rejected,
            "measurements": self.measurements,
            "significant_measurements": self.significant_measurements(),
            "verdict": self.verdict(),
        }

    def significant_measurements(self) -> list[str]:
        """Continuous channels that clear the pre-registered bar, by name."""
        return sorted(k for k, v in self.measurements.items() if v.get("attack_succeeds"))

    def verdict(self) -> str:
        if self.discriminators:
            return "ORACLE VIABLE — client-observable discriminator(s) found"
        if self.significant_measurements():
            return "ORACLE VIABLE — a continuous channel clears the pre-registered bar"
        return "NO CLIENT-OBSERVABLE SIGNAL — rescope FR-B-03 per LLD §7"


def probe_once(
    client: httpx.Client, gateway: str, prompt: str, tenant: str, api_key: str, label: str
) -> Probe:
    started = time.perf_counter()
    response = client.post(
        f"{gateway}/v1/completions",
        json={
            "model": "Qwen/Qwen2.5-0.5B-Instruct",
            "prompt": prompt,
            "max_tokens": 8,
            "temperature": 0.0,
        },
        headers={"Authorization": f"Bearer {api_key}", "x-llmd-tenant": tenant},
    )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    try:
        body = response.json()
    except ValueError:
        body = {}

    return Probe(
        label=label,
        prompt=prompt,
        tenant=tenant,
        status=response.status_code,
        elapsed_ms=elapsed_ms,
        # Every response header, verbatim. If a routing signal leaks through one
        # we did not anticipate, recording only the ones we expected would hide it.
        headers={k.lower(): v for k, v in response.headers.items()},
        body_keys=sorted(body.keys()),
        body_id=body.get("id"),
    )


#: Fixed here, not passed in, so a re-run cannot be reseeded until it says
#: something nicer. Same discipline as the ATTEST harness.
SPIKE_RNG_SEED = 20260907


def _is_numeric(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return True


def measure_numeric_channels(pairs: list[tuple[Probe, Probe]]) -> dict[str, dict[str, Any]]:
    """Judge every continuous channel by the pre-registered rule.

    Latency, and any header whose values are numbers, are *measurements*. Asking
    "did this field differ?" of a measurement is a category error — two timings
    essentially never coincide, so the answer is always yes and it means nothing.
    The question that means something was fixed in advance in
    `common.stats.decision`: does the value separate the two classes well enough,
    with a tight enough interval and a small enough p, to count as an oracle
    (NFR-05)?

    Applying that rule here is not a new decision. It is the decision this
    project already made, applied to the evidence it was written for.
    """
    from common.stats.decision import decide

    channels: dict[str, list[tuple[float, bool]]] = {"latency_ms": []}
    for hit, miss in pairs:
        channels["latency_ms"].append((hit.elapsed_ms, True))
        channels["latency_ms"].append((miss.elapsed_ms, False))
        for key in set(hit.headers) | set(miss.headers):
            values = [hit.headers.get(key), miss.headers.get(key)]
            if not all(v is not None and _is_numeric(v) for v in values):
                continue
            bucket = channels.setdefault(f"header:{key}", [])
            bucket.append((float(hit.headers[key]), True))
            bucket.append((float(miss.headers[key]), False))

    out: dict[str, dict[str, Any]] = {}
    for name, samples in channels.items():
        labels = [is_hit for _, is_hit in samples]
        if not any(labels) or all(labels):
            continue
        scores = [score for score, _ in samples]
        # Evaluated in BOTH orientations, keeping the stronger. An attacker who
        # notices that cache hits are the *slower* class simply inverts the test,
        # so scoring only one direction would report a perfect oracle as AUC 0.0
        # and call it clean. This is the attacker-favourable reading, which is
        # the conservative one for a security claim.
        forward = decide(labels, scores, rng_seed=SPIKE_RNG_SEED)  # type: ignore[arg-type]
        inverse = decide(labels, [-s for s in scores], rng_seed=SPIKE_RNG_SEED)  # type: ignore[arg-type]
        verdict, orientation = (
            (forward, "higher-is-hit") if forward.auc >= inverse.auc else (inverse, "lower-is-hit")
        )
        out[name] = {**verdict.to_dict(), "orientation": orientation}
    return out


# A field observed in fewer pairs than this cannot be told apart from noise: one
# observation of "these two differ" is consistent with both a perfect oracle and
# a millisecond counter. Below the threshold the field is kept, and the caller is
# expected to run enough repeats that the threshold is reached.
MIN_PAIRS_TO_JUDGE_VARIABILITY = 3


def find_discriminators(
    pairs: list[tuple[Probe, Probe]], rejected: dict[str, str] | None = None
) -> list[str]:
    """Fields that CLASSIFY a cache hit against a cache miss.

    Not "fields that differ" — that was the earlier implementation and it was
    wrong in a way that mattered. CI run #6 returned ORACLE VIABLE on
    ``x-envoy-upstream-service-time``, Envoy's per-request upstream latency in
    milliseconds. Two requests essentially never take the same number of
    milliseconds, so that header differs between *any* two probes and
    discriminates nothing. The same run recorded hit median 214.8 ms against
    miss median 214.5 ms on a simulator that by construction does not vary TTFT
    on cache hit versus miss (D-01) — so the timing carried no signal while the
    header derived from it was being counted as one.

    An ignore-list cannot fix that; it only names the noise you already thought
    of. So the test is now the one the docstring always claimed:

    * **consistent** — it differs in *every* pair, not merely some. A real
      oracle does not classify correctly nine times out of eleven.
    * **classifying** — its value is a property of the class, not of the
      request. A field that takes a fresh value on every single probe, on both
      sides, is measuring the request.

    This is a defect fix, not a change to the decision rule. LLD §7 fixes what
    the *verdict* means; it never said a differing field is a signal, and this
    function's own docstring already promised to exclude fields that "vary for
    reasons unrelated to routing".
    """
    ignore = {"date", "content-length", "x-request-id", "server", "connection"}
    if rejected is None:
        rejected = {}

    observed: dict[str, list[tuple[str | None, str | None]]] = {}
    for hit, miss in pairs:
        for key in set(hit.headers) | set(miss.headers):
            if key in ignore:
                continue
            observed.setdefault(key, []).append((hit.headers.get(key), miss.headers.get(key)))

    found: set[str] = set()
    for key, obs in observed.items():
        differing = sum(1 for h, m in obs if h != m)
        if differing == 0:
            continue

        values = [v for pair in obs for v in pair if v is not None]
        if values and all(_is_numeric(v) for v in values):
            # A measurement, not a label. It is not discarded — it is handed to
            # `measure_numeric_channels` and judged by the pre-registered rule in
            # `common.stats.decision`, which is what this project fixed in
            # advance for exactly this kind of evidence (NFR-05).
            rejected[f"header:{key}"] = (
                "numeric-valued, so a measurement rather than a categorical label; "
                "judged by the pre-registered AUC rule under measurements, not here"
            )
            continue

        if differing != len(obs):
            rejected[f"header:{key}"] = (
                f"differs in only {differing} of {len(obs)} hit/miss pairs; an oracle "
                "that classifies correctly only sometimes is not an oracle"
            )
            continue
        if len(obs) >= MIN_PAIRS_TO_JUDGE_VARIABILITY:
            hits = {h for h, _ in obs}
            misses = {m for _, m in obs}
            if hits & misses:
                shared = sorted(str(v) for v in (hits & misses))[:3]
                rejected[f"header:{key}"] = (
                    f"value(s) {shared} appear on both sides across {len(obs)} pairs, so "
                    "seeing one does not tell a caller which class produced it"
                )
                continue
        found.add(f"header:{key}")

    for hit, miss in pairs:
        if hit.body_keys != miss.body_keys:
            found.add("body:key-set")
    return sorted(found)


def run_spike(gateway: str, key_a: str, key_b: str, repeats: int, out_dir: Path) -> SpikeResult:
    result = SpikeResult()
    secret_prefix = (
        "Analyse the proposed acquisition of NORTHWIND MUTUAL by CALDER PARTNERS. "
        "Counterparty exposure summary follows. "
    ) * 4  # long enough to span several 16-token blocks
    control_prefix = ("Summarise the weather in the northern hemisphere for the coming week. ") * 4

    with httpx.Client(timeout=60.0) as client:
        # --- Step 1: self-collision baseline ---------------------------------
        # Tenant A sends the same prefix twice. Ground truth says the second is a
        # routing-index hit. If NOTHING the client can see differs between them,
        # there is no oracle to build — and that is the whole question.
        first = probe_once(client, gateway, secret_prefix + "one", "tenant-a", key_a, "self-1")
        second = probe_once(client, gateway, secret_prefix + "two", "tenant-a", key_a, "self-2")
        cold = probe_once(client, gateway, control_prefix + "x", "tenant-a", key_a, "cold")
        result.probes += [first, second, cold]

        pairs = [(second, cold)]

        # --- Step 2: cross-tenant probe --------------------------------------
        # Tenant B submits a prefix; tenant A probes for it and for a control.
        victim = probe_once(
            client, gateway, secret_prefix + "victim", "tenant-b", key_b, "victim-b"
        )
        result.probes.append(victim)
        time.sleep(1.0)

        for i in range(repeats):
            hit = probe_once(
                client, gateway, secret_prefix + "probe", "tenant-a", key_a, f"probe-hit-{i}"
            )
            miss = probe_once(
                client, gateway, control_prefix + "probe", "tenant-a", key_a, f"probe-miss-{i}"
            )
            result.probes += [hit, miss]
            pairs.append((hit, miss))

    result.discriminators = find_discriminators(pairs, result.rejected)
    result.measurements = measure_numeric_channels(pairs)

    hit_times = [p.elapsed_ms for p in result.probes if "hit" in p.label]
    miss_times = [p.elapsed_ms for p in result.probes if "miss" in p.label]
    if len(hit_times) >= 2 and len(miss_times) >= 2:
        result.notes.append(
            f"latency hit median={statistics.median(hit_times):.1f}ms "
            f"miss median={statistics.median(miss_times):.1f}ms — "
            "NOT evidence either way on the simulator, which does not vary TTFT "
            "on cache hit vs miss (D-01). Recorded for completeness only."
        )

    result.notes.append(
        "Ground truth must be read separately from the EPP's own metrics/logs. "
        "Compare it against the probes above before concluding: a spike that only "
        "looked client-side cannot tell 'no signal' from 'we did not look'."
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "spike-s02.json").write_text(
        json.dumps(result.to_dict(), indent=2, sort_keys=True), encoding="utf-8"
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", required=True, help="e.g. http://localhost:8080")
    parser.add_argument("--key-a", default="tenant-a-key")
    parser.add_argument("--key-b", default="tenant-b-key")
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--out", type=Path, default=Path("bench/results/spike-s02"))
    args = parser.parse_args(argv)

    try:
        result = run_spike(args.gateway, args.key_a, args.key_b, args.repeats, args.out)
    except httpx.HTTPError as exc:
        print(f"FAILED to reach the gateway at {args.gateway}: {exc}", file=sys.stderr)
        print("Is the cluster up? `make barrier-up`", file=sys.stderr)
        return 2

    print(f"\nraw evidence: {args.out / 'spike-s02.json'}")
    print(f"probes: {len(result.probes)}")
    for note in result.notes:
        print(f"  note: {note}")
    for name, reason in sorted(result.rejected.items()):
        print(f"  rejected: {name} — {reason}")
    print("\nmeasurements, by the pre-registered rule (NFR-05):")
    for name, verdict in sorted(result.measurements.items()):
        print(
            f"  {name}: AUC={verdict['auc']:.4f} "
            f"[{verdict['ci_lo']:.4f}, {verdict['ci_hi']:.4f}] "
            f"p={verdict['p_value']:.4g} n={verdict['n']} "
            f"clears_bar={verdict['attack_succeeds']}"
        )
    print(f"\nclient-observable discriminators: {result.discriminators or 'NONE'}")
    print(f"significant measurements: {result.significant_measurements() or 'NONE'}")
    print(f"\nVERDICT: {result.verdict()}")
    print(f"\n{DECISION_RULE}")
    print(
        "\nNext: read the EPP's routing metrics for the same window, confirm ground "
        "truth, then record the verdict as a mini-ADR in docs/design/decisions.md "
        "BEFORE any oracle code is written."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
