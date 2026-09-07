"""Calibration of the bootstrap interval, as a callable.

The property that establishes ``auc_bootstrap_ci`` is correct is *coverage*: over
many null datasets, a nominal 95% interval must contain the truth about 95% of the
time. A single null sample proves nothing, because a 95% interval is supposed to
miss one time in twenty.

The computation lived inside a test and was never published. It is here so that
the test and ``metrics/headline.py`` invoke the same function with the same seeds
and therefore report the same number. Everything is seeded; the result is a
deterministic function of its arguments.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from common.stats.auc import Labels, Scores, auc_bootstrap_ci
from common.stats.decision import CHANCE, CONFIDENCE


@dataclass(frozen=True)
class CoverageResult:
    """How often the interval contained the truth, and exactly how it was run."""

    trials: int
    hits: int
    nominal: float
    n_per_class: int
    n_resamples: int
    seed_base: int

    @property
    def coverage(self) -> float:
        return self.hits / self.trials


def null_dataset(n_per_class: int, seed: int) -> tuple[Labels, Scores]:
    """Two classes drawn from the same distribution: the true AUC is exactly 0.5."""
    rng = np.random.default_rng(seed)
    pos = rng.normal(0.0, 1.0, n_per_class)
    neg = rng.normal(0.0, 1.0, n_per_class)
    labels = np.concatenate([np.ones(n_per_class, bool), np.zeros(n_per_class, bool)])
    return labels, np.concatenate([pos, neg])


def bootstrap_coverage(
    *,
    trials: int = 200,
    n_per_class: int = 50,
    n_resamples: int = 200,
    seed_base: int = 1000,
    confidence: float = CONFIDENCE,
) -> CoverageResult:
    """Fraction of ``trials`` null datasets whose bootstrap interval contains 0.5.

    Dataset ``i`` is drawn with seed ``seed_base + i`` and resampled with seed
    ``i``, so two calls with the same arguments return the same result.
    """
    if trials < 1:
        raise ValueError(f"trials must be positive, got {trials}")

    hits = 0
    for i in range(trials):
        labels, scores = null_dataset(n_per_class, seed_base + i)
        _, lo, hi = auc_bootstrap_ci(
            labels, scores, n_resamples=n_resamples, confidence=confidence, rng_seed=i
        )
        hits += int(lo <= CHANCE <= hi)

    return CoverageResult(
        trials=trials,
        hits=hits,
        nominal=confidence,
        n_per_class=n_per_class,
        n_resamples=n_resamples,
        seed_base=seed_base,
    )
