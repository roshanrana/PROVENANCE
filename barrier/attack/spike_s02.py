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

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_rule": DECISION_RULE,
            "probes": [p.to_dict() for p in self.probes],
            "notes": self.notes,
            "client_observable_discriminators": self.discriminators,
            "verdict": self.verdict(),
        }

    def verdict(self) -> str:
        if self.discriminators:
            return "ORACLE VIABLE — client-observable discriminator(s) found"
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


def find_discriminators(pairs: list[tuple[Probe, Probe]]) -> list[str]:
    """Fields that differ between a cache-hit probe and a cache-miss probe.

    Ignores fields that vary for reasons unrelated to routing — a per-request id
    or a timestamp differs on every call and discriminates nothing.
    """
    ignore = {"date", "content-length", "x-request-id", "server", "connection"}
    found: set[str] = set()

    for hit, miss in pairs:
        for key in set(hit.headers) | set(miss.headers):
            if key in ignore:
                continue
            if hit.headers.get(key) != miss.headers.get(key):
                found.add(f"header:{key}")
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

    result.discriminators = find_discriminators(pairs)

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
    print(f"\nclient-observable discriminators: {result.discriminators or 'NONE'}")
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
