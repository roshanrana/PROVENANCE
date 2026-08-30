"""The pre-registered decision rule.

**These thresholds are NFR-05 and they were fixed before any attack code existed.**
Moving one is not a code change — it is the project marking its own homework, and
`tests/common/test_decision_thresholds.py` asserts their exact values so a quiet
edit fails the build.

There is one implementation of this rule, used by both the attack evaluation and
the mitigation evaluation. Two implementations would make the comparison between
them meaningless, which is the entire result BARRIER is trying to establish.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from common.stats.auc import Labels, Scores, auc_bootstrap_ci
from common.stats.permutation import permutation_p

#: An attack "succeeds" only if all three hold.
AUC_SUCCESS_THRESHOLD = 0.75
P_VALUE_THRESHOLD = 0.01
CONFIDENCE = 0.95

#: Chance level. The mitigation succeeds when the interval straddles this.
CHANCE = 0.5

DEFAULT_RESAMPLES = 10_000
DEFAULT_PERMUTATIONS = 10_000


@dataclass(frozen=True)
class Verdict:
    """The published result. Emitted verbatim — never paraphrased into prose."""

    auc: float
    ci_lo: float
    ci_hi: float
    p_value: float
    n: int
    n_positive: int
    n_negative: int
    seed: int
    attack_succeeds: bool
    at_chance: bool

    def summary(self) -> str:
        return (
            f"AUC={self.auc:.4f} "
            f"[{self.ci_lo:.4f}, {self.ci_hi:.4f}] "
            f"p={self.p_value:.4g} n={self.n} seed={self.seed} "
            f"attack_succeeds={self.attack_succeeds} at_chance={self.at_chance}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "auc": self.auc,
            "ci_lo": self.ci_lo,
            "ci_hi": self.ci_hi,
            "p_value": self.p_value,
            "n": self.n,
            "n_positive": self.n_positive,
            "n_negative": self.n_negative,
            "seed": self.seed,
            "attack_succeeds": self.attack_succeeds,
            "at_chance": self.at_chance,
            "thresholds": {
                "auc_success": AUC_SUCCESS_THRESHOLD,
                "p_value": P_VALUE_THRESHOLD,
                "confidence": CONFIDENCE,
            },
        }


def decide(
    labels: Labels,
    scores: Scores,
    *,
    rng_seed: int,
    n_resamples: int = DEFAULT_RESAMPLES,
    n_permutations: int = DEFAULT_PERMUTATIONS,
) -> Verdict:
    """Apply the pre-registered rule to one set of observations.

    ``attack_succeeds`` and ``at_chance`` are deliberately **not** complements.
    A result can be neither — an oracle better than chance but below the bar — and
    collapsing that into a binary would let a weak positive be reported as either
    a success or a clean mitigation depending on which claim was convenient.
    """
    import numpy as np

    labels_arr = np.asarray(labels, dtype=bool)
    point, lo, hi = auc_bootstrap_ci(
        labels_arr, scores, n_resamples=n_resamples, confidence=CONFIDENCE, rng_seed=rng_seed
    )
    p_value = permutation_p(labels_arr, scores, n_permutations=n_permutations, rng_seed=rng_seed)

    n_positive = int(labels_arr.sum())
    return Verdict(
        auc=point,
        ci_lo=lo,
        ci_hi=hi,
        p_value=p_value,
        n=int(labels_arr.size),
        n_positive=n_positive,
        n_negative=int(labels_arr.size - n_positive),
        seed=rng_seed,
        attack_succeeds=(
            point >= AUC_SUCCESS_THRESHOLD and lo > CHANCE and p_value < P_VALUE_THRESHOLD
        ),
        at_chance=(lo <= CHANCE <= hi),
    )
