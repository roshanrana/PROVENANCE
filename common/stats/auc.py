"""AUC and its bootstrap confidence interval.

Implemented here rather than imported (ADR-003) because NFR-05 makes this test a
headline claim of the project: a reviewer assessing whether the security result
holds should be able to read the test, not trust a library call.

Correctness notes that matter, and that a casual implementation gets wrong:

* **Ties.** AUC is computed from *average* ranks (the Mann-Whitney U identity).
  A naive pairwise count that treats ties as wins inflates the score, and a timing
  oracle produces ties constantly — quantised clocks, repeated bucket values.
* **Stratified resampling.** The bootstrap resamples the positive and negative
  classes separately. Pooled resampling can produce a replicate with zero
  positives, where AUC is undefined, and silently dropping those biases the
  interval toward the middle.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.stats import rankdata

Labels = NDArray[np.bool_]
Scores = NDArray[np.float64]


class InsufficientData(ValueError):
    """Both classes must be present for AUC to be defined."""


def _validate(labels: Labels, scores: Scores) -> tuple[Labels, Scores]:
    labels_arr = np.asarray(labels, dtype=bool)
    scores_arr = np.asarray(scores, dtype=np.float64)
    if labels_arr.shape != scores_arr.shape:
        raise ValueError(
            f"labels and scores must have the same shape: {labels_arr.shape} != {scores_arr.shape}"
        )
    if labels_arr.ndim != 1:
        raise ValueError(f"expected 1-D input, got shape {labels_arr.shape}")
    if not np.all(np.isfinite(scores_arr)):
        raise ValueError("scores contain NaN or infinity")
    n_pos = int(labels_arr.sum())
    n_neg = int(labels_arr.size - n_pos)
    if n_pos == 0 or n_neg == 0:
        raise InsufficientData(
            f"AUC needs both classes present (positives={n_pos}, negatives={n_neg})"
        )
    return labels_arr, scores_arr


def auc(labels: Labels, scores: Scores) -> float:
    """Area under the ROC curve, via the Mann-Whitney U identity.

    Equals the probability that a randomly chosen positive scores above a
    randomly chosen negative, counting ties as one half.
    """
    labels_arr, scores_arr = _validate(labels, scores)
    n_pos = int(labels_arr.sum())
    n_neg = int(labels_arr.size - n_pos)

    ranks = rankdata(scores_arr)  # average ranks — this is what handles ties
    rank_sum_pos = float(ranks[labels_arr].sum())
    u = rank_sum_pos - n_pos * (n_pos + 1) / 2.0
    return float(u / (n_pos * n_neg))


def auc_bootstrap_ci(
    labels: Labels,
    scores: Scores,
    *,
    n_resamples: int = 10_000,
    confidence: float = 0.95,
    rng_seed: int,
) -> tuple[float, float, float]:
    """Return ``(point_estimate, ci_low, ci_high)`` by stratified percentile bootstrap.

    ``rng_seed`` is required, not optional: NFR-03 says the analysis must be
    reproducible, and a default seed is how an irreproducible number gets
    published by accident.
    """
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")
    if n_resamples < 1:
        raise ValueError(f"n_resamples must be positive, got {n_resamples}")

    labels_arr, scores_arr = _validate(labels, scores)
    point = auc(labels_arr, scores_arr)

    pos_scores = scores_arr[labels_arr]
    neg_scores = scores_arr[~labels_arr]
    n_pos, n_neg = pos_scores.size, neg_scores.size

    rng = np.random.default_rng(rng_seed)
    replicates = np.empty(n_resamples, dtype=np.float64)
    template = np.concatenate([np.ones(n_pos, dtype=bool), np.zeros(n_neg, dtype=bool)])

    for i in range(n_resamples):
        resampled = np.concatenate(
            [
                rng.choice(pos_scores, size=n_pos, replace=True),
                rng.choice(neg_scores, size=n_neg, replace=True),
            ]
        )
        replicates[i] = auc(template, resampled)

    alpha = 1.0 - confidence
    low, high = np.quantile(replicates, [alpha / 2.0, 1.0 - alpha / 2.0])
    return point, float(low), float(high)
