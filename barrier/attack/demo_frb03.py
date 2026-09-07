"""FR-B-03 — the cross-tenant leak, measured one request at a time.

ADR-011 rescoped this from an attacker-observable oracle to an
operator-instrumented demonstration, because S-02 established that a client sees
nothing on the simulator. Run #13 then showed why the obvious instrument does not
work either: the aggregate prefix hit ratio was 0.990 under `default` and 0.989
under `hardened`, because the S-02 schedule is tenant A repeating its *own*
prefix two hundred times and exactly one probe in the run is a genuine
cross-tenant test.

So this measures the one event that matters, in isolation, and repeats it.

**The instrument.** `prefix_indexer_hit_ratio` is a histogram. Its `_sum` and
`_count` are cumulative, so around a single request

    (sum_after - sum_before) / (count_after - count_before)

is *that request's own* match ratio, provided the count moved by exactly one.
This module refuses to record a trial where it moved by anything else — another
client, a retry, or a scheduling cycle we do not understand would each silently
corrupt the attribution, and a corrupted attribution here would be published as
a security result.

**The schedule.** Each trial uses a fresh nonce, so no trial can hit an earlier
one's entries:

1. **Tenant B plants** ``<nonce> <filler>`` — the victim's prompt.
2. **Tenant A probes** the same text. Under a shared namespace this is a hit on
   another tenant's blocks. Positive class.
3. **Tenant A controls** with a *different* fresh nonce nobody has sent.
   Negative class.

Both classes are tenant A, same key, same length, same shape, sent back to back.
The only difference is whether another tenant put that prefix in the index. That
is the leak stated as an experiment.

**The verdict** comes from `common.stats.decision`, the same pre-registered rule
(NFR-05) used everywhere else in this project and unchanged since before any
attack code existed:

* run under `default`  — the attack succeeds if it clears the bar;
* run under `hardened` — the mitigation succeeds if the interval straddles
  chance.

**Both halves are required.** A default run that clears the bar with no hardened
comparison shows a leak nobody closed; a hardened run at chance with no default
comparison is indistinguishable from a broken cluster.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx

from barrier.attack.ground_truth import read_ground_truth

#: Fixed, not a flag. A re-run cannot be reseeded until it says something nicer.
DEMO_RNG_SEED = 20260907

#: Upstream clamps the approximate indexer's block size to a minimum of 64
#: tokens, so a prefix shorter than that cannot register a meaningful match and
#: the experiment would measure the block size rather than the leak.
_FILLER = (
    "Counterparty exposure summary follows. Positions are held across the "
    "consolidated book and are reconciled nightly against the custodian record. "
    "Valuation uses end-of-day marks with a two-day settlement assumption. "
) * 3


class DemoError(RuntimeError):
    """Raised when a trial cannot be attributed, rather than guessed at."""


@dataclass
class Trial:
    index: int
    nonce: str
    #: Match ratio the index attributed to tenant A's probe of tenant B's prefix.
    probe_ratio: float
    #: Match ratio for the same tenant, same shape, prefix nobody planted.
    control_ratio: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DemoResult:
    profile: str
    trials: list[Trial] = field(default_factory=list)
    verdict: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "seed": DEMO_RNG_SEED,
            "trials": [t.to_dict() for t in self.trials],
            "verdict": self.verdict,
            "notes": self.notes,
        }


def _index_state(client: httpx.Client, metrics_url: str) -> tuple[int, float]:
    response = client.get(metrics_url)
    response.raise_for_status()
    truth = read_ground_truth(response.text)
    # The check is that the metric EXISTS, not that it is non-zero: a cluster
    # whose index has legitimately never been consulted reads zero, and refusing
    # that would make the demonstration unable to run first. An absent family is
    # different — it means there is no index to attribute anything to.
    if not truth.family:
        raise DemoError(
            "the EPP publishes no prefix_indexer_hit_ratio metric; there is "
            "no index to attribute anything to"
        )
    return truth.lookups, truth.ratio_sum


def _send(client: httpx.Client, gateway: str, prompt: str, key: str) -> None:
    response = client.post(
        f"{gateway}/v1/completions",
        json={
            "model": "Qwen/Qwen2.5-0.5B-Instruct",
            "prompt": prompt,
            "max_tokens": 8,
            "temperature": 0.0,
        },
        headers={"Authorization": f"Bearer {key}"},
    )
    if response.status_code != 200:
        raise DemoError(
            f"gateway answered {response.status_code} for a tenant request; the "
            "demonstration cannot attribute an index lookup to a request that "
            "was never routed"
        )


def _attributed_ratio(
    client: httpx.Client, gateway: str, metrics_url: str, prompt: str, key: str
) -> float:
    """Send one request and return the match ratio the index attributed to it."""
    count_before, sum_before = _index_state(client, metrics_url)
    _send(client, gateway, prompt, key)

    # The producer records asynchronously with respect to the HTTP response, so
    # the counter can lag it. Polled rather than slept: a fixed sleep is either
    # slow or racy, and a race here corrupts an attribution silently.
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        count_after, sum_after = _index_state(client, metrics_url)
        if count_after > count_before:
            break
        time.sleep(0.05)
    else:
        raise DemoError("the index recorded no lookup for a request that returned 200")

    moved = count_after - count_before
    if moved != 1:
        raise DemoError(
            f"the index recorded {moved} lookups for one request. Per-request "
            "attribution is only valid at exactly one; something else is talking "
            "to this cluster, or a request maps to more than one lookup and this "
            "measurement needs rethinking rather than rescaling"
        )
    return sum_after - sum_before


def run_demo(
    *,
    gateway: str,
    metrics_url: str,
    key_a: str,
    key_b: str,
    profile: str,
    trials: int,
    client: httpx.Client | None = None,
) -> DemoResult:
    from common.stats.decision import decide

    result = DemoResult(profile=profile)
    owned = client is None
    http = client or httpx.Client(timeout=60.0)
    try:
        for i in range(trials):
            nonce = secrets.token_hex(8)
            victim = f"{nonce} {_FILLER}"
            control = f"{secrets.token_hex(8)} {_FILLER}"

            # Tenant B plants. Its own attribution is not recorded — the claim is
            # about what tenant A can reach, not about what tenant B did.
            _attributed_ratio(http, gateway, metrics_url, victim, key_b)

            probe = _attributed_ratio(http, gateway, metrics_url, victim, key_a)
            ctrl = _attributed_ratio(http, gateway, metrics_url, control, key_a)
            result.trials.append(Trial(index=i, nonce=nonce, probe_ratio=probe, control_ratio=ctrl))
    finally:
        if owned:
            http.close()

    labels = [True] * len(result.trials) + [False] * len(result.trials)
    scores = [t.probe_ratio for t in result.trials] + [t.control_ratio for t in result.trials]
    verdict = decide(labels, scores, rng_seed=DEMO_RNG_SEED)  # type: ignore[arg-type]
    result.verdict = verdict.to_dict()

    result.notes.append(
        "Positive class: tenant A probing a prefix tenant B planted. Negative "
        "class: tenant A probing a prefix nobody planted. Same tenant, same key, "
        "same length, sent back to back — the only difference is who else had "
        "seen the text."
    )
    result.notes.append(
        "Read with the profile. Under `default` the attack succeeds if this "
        "clears the pre-registered bar; under `hardened` the mitigation succeeds "
        "if the interval straddles chance. Neither half means anything alone."
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", required=True)
    parser.add_argument("--metrics", required=True, help="the EPP's /metrics URL")
    parser.add_argument("--key-a", required=True)
    parser.add_argument("--key-b", required=True)
    parser.add_argument("--profile", required=True, choices=["default", "hardened"])
    parser.add_argument("--trials", type=int, default=40)
    parser.add_argument("--out", type=Path, default=Path("bench/results/frb03"))
    args = parser.parse_args(argv)

    try:
        result = run_demo(
            gateway=args.gateway,
            metrics_url=args.metrics,
            key_a=args.key_a,
            key_b=args.key_b,
            profile=args.profile,
            trials=args.trials,
        )
    except (DemoError, httpx.HTTPError) as exc:
        print(f"FR-B-03 FAILED: {exc}", file=sys.stderr)
        return 2

    out_dir = args.out / args.profile
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "frb03.json").write_text(
        json.dumps(result.to_dict(), indent=2, sort_keys=True), encoding="utf-8"
    )

    probes = [t.probe_ratio for t in result.trials]
    controls = [t.control_ratio for t in result.trials]
    print(f"\nFR-B-03 ({args.profile}) — {len(result.trials)} trials")
    print(f"  raw evidence: {out_dir / 'frb03.json'}")
    print(f"  cross-tenant probe match ratio: mean {sum(probes) / len(probes):.4f}")
    print(f"  control match ratio:            mean {sum(controls) / len(controls):.4f}")
    print(
        f"\n  {result.verdict['auc']:.4f} AUC "
        f"[{result.verdict['ci_lo']:.4f}, {result.verdict['ci_hi']:.4f}] "
        f"p={result.verdict['p_value']:.4g} n={result.verdict['n']}"
    )
    print(
        f"  attack_succeeds={result.verdict['attack_succeeds']} "
        f"at_chance={result.verdict['at_chance']}"
    )
    for note in result.notes:
        print(f"  note: {note}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
