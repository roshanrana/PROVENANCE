"""Two-sided permutation test for an AUC result.

The null hypothesis is that the scores carry no information about the labels —
that is, AUC = 0.5. Under that null, any assignment of labels to scores is equally
likely, so shuffling the labels and recomputing AUC samples the null distribution
directly. No distributional assumption is needed, which is the point: the timing
distributions BARRIER measures are not normal, and asserting that they were would
be the kind of unexamined assumption that makes a benchmark unconvincing.
"""

from __future__ import annotations

import numpy as np

from common.stats.auc import Labels, Scores, _validate, auc


def permutation_p(
    labels: Labels,
    scores: Scores,
    *,
    n_permutations: int = 10_000,
    rng_seed: int,
) -> float:
    """Two-sided p-value for ``AUC != 0.5``.

    Uses the add-one correction: the observed arrangement is itself one of the
    possible permutations, so the numerator and denominator both include it. That
    makes the smallest reportable p-value ``1 / (n_permutations + 1)`` rather than
    zero — and a reported p of exactly 0 is never honest, it just means the
    resolution ran out.
    """
    if n_permutations < 1:
        raise ValueError(f"n_permutations must be positive, got {n_permutations}")

    labels_arr, scores_arr = _validate(labels, scores)
    observed = abs(auc(labels_arr, scores_arr) - 0.5)

    rng = np.random.default_rng(rng_seed)
    shuffled = labels_arr.copy()
    at_least_as_extreme = 0
    for _ in range(n_permutations):
        rng.shuffle(shuffled)
        if abs(auc(shuffled, scores_arr) - 0.5) >= observed:
            at_least_as_extreme += 1

    return (at_least_as_extreme + 1) / (n_permutations + 1)
