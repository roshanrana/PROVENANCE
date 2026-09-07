"""Did the router actually have anything to leak?

S-02 asks whether an ordinary caller can observe a routing signal. A verdict of
NO CLIENT-OBSERVABLE SIGNAL is worth exactly what its positive control is worth,
and the spike says so itself on every run: *a spike that only looked client-side
cannot tell "no signal" from "we did not look"*.

The control is the EPP's own prefix index. If it never recorded a match — the
producer never ran, or every lookup matched zero tokens — then the run measured
a misconfigured cluster and would have published it as a security property. That
is the F-14 / F-19 shape: a check that passed because it was run against the
thing that accommodates it.

The first version of this gate only asserted that the string "prefix" appeared
somewhere in the metrics. It passed on
``inference_extension_plugin_duration_seconds{plugin_name="approx-prefix-cache-producer"}``
— which proves a plugin *by that name* executed, and nothing whatsoever about
whether it ever matched a prefix (F-26). This module asserts the thing itself.

The metric is a histogram of match ratios. Upstream publishes it twice, under a
deprecated ``inference_extension_`` name and an ``llm_d_router_epp_`` one, so
any family whose name ends in ``prefix_indexer_hit_ratio`` counts. Its first
bucket is ``le="0"``: observations there matched *nothing*. So

    observations - le("0") = lookups that matched a non-zero prefix

and that number being positive is the whole control.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

HIT_RATIO_SUFFIX = "prefix_indexer_hit_ratio"
INDEX_SIZE_SUFFIX = "prefix_indexer_size"

_SAMPLE = re.compile(r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)(?P<labels>\{[^}]*\})?\s+(?P<value>\S+)$")
_LE = re.compile(r'\ble="([^"]*)"')


@dataclass(frozen=True)
class GroundTruth:
    """What the EPP's own index says happened, independent of the client."""

    lookups: int
    matched_nothing: int
    index_size: float | None
    #: The histogram's `_sum` — total matched ratio across all lookups. Useless
    #: as an aggregate (see run #13) but the numerator of the per-request
    #: attribution FR-B-03 is built on: sum-delta over count-delta around a
    #: single request is that request's own match ratio.
    ratio_sum: float = 0.0
    #: Which metric family these counts came from, so the number in the log can
    #: be checked against the dump. Reported per family rather than summed: the
    #: two published families are the SAME observations under two names, and a
    #: summed "consulted 128 times" for 64 probes is a number a reader would
    #: rightly distrust.
    family: str = ""

    @property
    def matched_something(self) -> int:
        return self.lookups - self.matched_nothing

    @property
    def holds(self) -> bool:
        """The control is satisfied: the index was consulted and it matched."""
        return self.lookups > 0 and self.matched_something > 0

    def summary(self) -> str:
        if self.lookups == 0:
            return "prefix index NEVER CONSULTED — no prefix_indexer_hit_ratio observations"
        size = "unknown" if self.index_size is None else f"{self.index_size:g}"
        where = f" [{self.family}]" if self.family else ""
        return (
            f"prefix index consulted {self.lookups} times, "
            f"{self.matched_something} matched a non-zero prefix, "
            f"{self.matched_nothing} matched nothing; index size {size}{where}"
        )


def _parse_samples(text: str) -> list[tuple[str, str, float]]:
    out: list[tuple[str, str, float]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _SAMPLE.match(line)
        if m is None:
            continue
        try:
            value = float(m["value"])
        except ValueError:
            continue
        out.append((m["name"], m["labels"] or "", value))
    return out


def read_ground_truth(text: str) -> GroundTruth:
    """Extract the control from a Prometheus exposition dump.

    Upstream publishes the histogram twice — a deprecated `inference_extension_`
    name and an `llm_d_epp_` one — carrying identical observations. Each family
    is read separately and the one with the most observations is returned, so
    the reported count matches the number of probes a reader can see in the
    spike output. Summing them reported "consulted 128 times" for 64 probes,
    which is a number that invites distrust of the whole gate.

    Matching by *suffix* rather than by full name is deliberate: an upstream
    rename must not silently disarm the control, which is the failure this
    module exists to prevent.
    """
    lookups: dict[str, float] = {}
    matched_nothing: dict[str, float] = {}
    ratio_sum: dict[str, float] = {}
    index_size: float | None = None

    for name, labels, value in _parse_samples(text):
        if name.endswith(INDEX_SIZE_SUFFIX):
            index_size = value if index_size is None else max(index_size, value)
        elif name.endswith(f"{HIT_RATIO_SUFFIX}_count"):
            family = name[: -len("_count")]
            lookups[family] = lookups.get(family, 0.0) + value
        elif name.endswith(f"{HIT_RATIO_SUFFIX}_sum"):
            family = name[: -len("_sum")]
            ratio_sum[family] = ratio_sum.get(family, 0.0) + value
        elif name.endswith(f"{HIT_RATIO_SUFFIX}_bucket"):
            le = _LE.search(labels)
            # The zero bucket, however Prometheus chose to format it.
            if le is not None and _is_zero(le.group(1)):
                family = name[: -len("_bucket")]
                matched_nothing[family] = matched_nothing.get(family, 0.0) + value

    if not lookups:
        return GroundTruth(lookups=0, matched_nothing=0, index_size=index_size)

    family = max(lookups, key=lambda k: lookups[k])
    return GroundTruth(
        lookups=int(lookups[family]),
        matched_nothing=int(matched_nothing.get(family, 0.0)),
        index_size=index_size,
        ratio_sum=ratio_sum.get(family, 0.0),
        family=family,
    )


def _is_zero(le: str) -> bool:
    try:
        return float(le) == 0.0
    except ValueError:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("metrics", type=Path, help="a Prometheus exposition dump from the EPP")
    args = parser.parse_args(argv)

    if not args.metrics.is_file():
        print(f"GROUND TRUTH MISSING: {args.metrics} does not exist", file=sys.stderr)
        return 5

    truth = read_ground_truth(args.metrics.read_text(encoding="utf-8", errors="replace"))
    print(f"ground truth: {truth.summary()}")
    if truth.holds:
        return 0

    print(
        "GROUND TRUTH FAILS. The EPP's prefix index recorded no match, so this run\n"
        "  cannot distinguish 'no client-observable signal' from 'the router never\n"
        "  indexed a prefix'. The spike's verdict must NOT be recorded from it.",
        file=sys.stderr,
    )
    return 5


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
