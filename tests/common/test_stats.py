"""Statistics — the tests a `verifier-critical` pass would demand.

Checked against known reference values, not merely for absence of exceptions. A
statistic wrong in the fourth decimal still invalidates the claim it supports.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.stats import mannwhitneyu

from common.stats.auc import InsufficientData, auc, auc_bootstrap_ci
from common.stats.decision import (
    AUC_SUCCESS_THRESHOLD,
    CHANCE,
    CONFIDENCE,
    P_VALUE_THRESHOLD,
    decide,
)
from common.stats.noise import (
    measure_noise_floor,
    required_trials,
    required_trials_for_auc,
)
from common.stats.permutation import permutation_p

# --------------------------------------------------------------------------- AUC


def test_perfect_separation_is_one() -> None:
    labels = np.array([False, False, True, True])
    scores = np.array([0.1, 0.2, 0.8, 0.9])
    assert auc(labels, scores) == 1.0


def test_perfect_inversion_is_zero() -> None:
    labels = np.array([False, False, True, True])
    scores = np.array([0.9, 0.8, 0.2, 0.1])
    assert auc(labels, scores) == 0.0


def test_all_ties_is_exactly_one_half() -> None:
    """Every score identical carries no information. Ties count as half.

    A pairwise implementation that scores ties as wins returns 1.0 here — and a
    timing oracle on a quantised clock produces ties constantly, so this is the
    failure mode that would silently manufacture a result.
    """
    labels = np.array([True, True, False, False])
    scores = np.array([5.0, 5.0, 5.0, 5.0])
    assert auc(labels, scores) == 0.5


def test_partial_ties_are_handled_as_half_credit() -> None:
    labels = np.array([True, False])
    scores = np.array([1.0, 1.0])
    assert auc(labels, scores) == 0.5


def test_matches_scipy_mannwhitneyu_on_random_data() -> None:
    """Reference check against an independent implementation."""
    rng = np.random.default_rng(20260829)
    for _ in range(25):
        n_pos, n_neg = int(rng.integers(3, 40)), int(rng.integers(3, 40))
        pos = rng.normal(0.6, 1.0, n_pos)
        neg = rng.normal(0.0, 1.0, n_neg)
        labels = np.concatenate([np.ones(n_pos, bool), np.zeros(n_neg, bool)])
        scores = np.concatenate([pos, neg])

        u = mannwhitneyu(pos, neg, alternative="two-sided").statistic
        assert auc(labels, scores) == pytest.approx(u / (n_pos * n_neg), abs=1e-12)


def test_matches_scipy_even_with_heavy_ties() -> None:
    """Ties are where implementations diverge, so they get their own reference check."""
    rng = np.random.default_rng(7)
    pos = rng.integers(0, 3, 40).astype(float)  # only 3 distinct values
    neg = rng.integers(0, 3, 40).astype(float)
    labels = np.concatenate([np.ones(40, bool), np.zeros(40, bool)])
    scores = np.concatenate([pos, neg])
    u = mannwhitneyu(pos, neg, alternative="two-sided").statistic
    assert auc(labels, scores) == pytest.approx(u / 1600, abs=1e-12)


def test_auc_is_invariant_under_monotone_rescaling() -> None:
    """AUC is rank-based: units must not matter (seconds vs milliseconds)."""
    labels = np.array([True, True, False, False])
    scores = np.array([0.30, 0.25, 0.10, 0.05])
    assert auc(labels, scores) == auc(labels, scores * 1000.0)


def test_single_class_is_refused() -> None:
    with pytest.raises(InsufficientData):
        auc(np.array([True, True]), np.array([1.0, 2.0]))


def test_shape_mismatch_is_refused() -> None:
    with pytest.raises(ValueError, match="same shape"):
        auc(np.array([True, False]), np.array([1.0]))


def test_non_finite_scores_are_refused() -> None:
    with pytest.raises(ValueError, match="NaN or infinity"):
        auc(np.array([True, False]), np.array([1.0, np.nan]))


# --------------------------------------------------------------------------- bootstrap


def _separated(n: int, shift: float, seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    pos = rng.normal(shift, 1.0, n)
    neg = rng.normal(0.0, 1.0, n)
    labels = np.concatenate([np.ones(n, bool), np.zeros(n, bool)])
    return labels, np.concatenate([pos, neg])


def test_bootstrap_is_deterministic_for_a_fixed_seed() -> None:
    labels, scores = _separated(60, 1.0, 1)
    a = auc_bootstrap_ci(labels, scores, n_resamples=500, rng_seed=42)
    b = auc_bootstrap_ci(labels, scores, n_resamples=500, rng_seed=42)
    assert a == b


def test_bootstrap_differs_across_seeds() -> None:
    labels, scores = _separated(60, 1.0, 1)
    a = auc_bootstrap_ci(labels, scores, n_resamples=500, rng_seed=1)
    b = auc_bootstrap_ci(labels, scores, n_resamples=500, rng_seed=2)
    assert a[1:] != b[1:]  # point estimate identical; interval is resampled


def test_interval_brackets_the_point_estimate() -> None:
    labels, scores = _separated(80, 1.2, 3)
    point, lo, hi = auc_bootstrap_ci(labels, scores, n_resamples=800, rng_seed=7)
    assert lo <= point <= hi


def test_interval_excludes_chance_when_signal_is_strong() -> None:
    labels, scores = _separated(120, 2.0, 5)
    _, lo, _ = auc_bootstrap_ci(labels, scores, n_resamples=800, rng_seed=11)
    assert lo > CHANCE


def test_interval_contains_chance_when_there_is_no_signal() -> None:
    labels, scores = _separated(120, 0.0, 17)
    _, lo, hi = auc_bootstrap_ci(labels, scores, n_resamples=800, rng_seed=11)
    assert lo <= CHANCE <= hi


@pytest.mark.slow
def test_bootstrap_interval_is_calibrated() -> None:
    """A 95% interval must contain the truth about 95% of the time.

    This is the test that actually establishes the bootstrap is correct. A single
    null sample proves nothing: an earlier version of the test above asserted
    coverage on one fixed seed and failed, because a 95% interval is *supposed* to
    miss one time in twenty. Coverage is the property; a single draw is an anecdote.
    """
    trials, hits = 200, 0
    for i in range(trials):
        labels, scores = _separated(50, 0.0, 1000 + i)
        _, lo, hi = auc_bootstrap_ci(labels, scores, n_resamples=200, rng_seed=i)
        hits += lo <= CHANCE <= hi

    coverage = hits / trials
    # Generous band: 200 trials of a nominal-95% procedure has a standard error of
    # about 1.5pp, and the percentile bootstrap is only asymptotically exact.
    assert 0.88 <= coverage <= 0.99, f"coverage {coverage:.3f} is not near nominal 95%"


def test_wider_interval_for_smaller_samples() -> None:
    small = auc_bootstrap_ci(*_separated(15, 1.0, 9), n_resamples=800, rng_seed=3)
    large = auc_bootstrap_ci(*_separated(300, 1.0, 9), n_resamples=800, rng_seed=3)
    assert (small[2] - small[1]) > (large[2] - large[1])


def test_stratification_keeps_class_balance_under_extreme_imbalance() -> None:
    """With 3 positives, pooled resampling would sometimes draw none at all."""
    labels = np.array([True] * 3 + [False] * 200)
    rng = np.random.default_rng(0)
    scores = np.concatenate([rng.normal(3, 1, 3), rng.normal(0, 1, 200)])
    point, lo, hi = auc_bootstrap_ci(labels, scores, n_resamples=500, rng_seed=1)
    assert 0.0 <= lo <= point <= hi <= 1.0


def test_invalid_confidence_is_refused() -> None:
    labels, scores = _separated(10, 1.0, 1)
    with pytest.raises(ValueError, match="confidence"):
        auc_bootstrap_ci(labels, scores, confidence=1.5, rng_seed=1)


# --------------------------------------------------------------------------- permutation


def test_permutation_is_deterministic_for_a_fixed_seed() -> None:
    labels, scores = _separated(40, 1.0, 2)
    args = {"n_permutations": 400, "rng_seed": 5}
    assert permutation_p(labels, scores, **args) == permutation_p(labels, scores, **args)


def test_strong_signal_gives_a_small_p_value() -> None:
    labels, scores = _separated(80, 2.5, 4)
    assert permutation_p(labels, scores, n_permutations=1000, rng_seed=1) < 0.01


def test_no_signal_gives_a_large_p_value() -> None:
    labels, scores = _separated(80, 0.0, 4)
    assert permutation_p(labels, scores, n_permutations=1000, rng_seed=1) > 0.05


def test_p_value_is_never_zero() -> None:
    """The add-one correction. A reported p of exactly 0 is not honesty, it is
    running out of resolution."""
    labels = np.array([True] * 30 + [False] * 30)
    scores = np.concatenate([np.full(30, 10.0), np.full(30, -10.0)])
    p = permutation_p(labels, scores, n_permutations=200, rng_seed=1)
    assert p == pytest.approx(1 / 201)
    assert p > 0


def test_test_is_two_sided() -> None:
    """An inverted oracle is still an oracle: AUC well below 0.5 must be significant."""
    labels, scores = _separated(80, 2.5, 4)
    inverted = -scores
    assert auc(labels, inverted) < 0.2
    assert permutation_p(labels, inverted, n_permutations=1000, rng_seed=1) < 0.01


# --------------------------------------------------------------------------- decision


def test_thresholds_are_exactly_the_pre_registered_values() -> None:
    """NFR-05, pinned. If a threshold moved, the project is marking its own homework."""
    assert AUC_SUCCESS_THRESHOLD == 0.75
    assert P_VALUE_THRESHOLD == 0.01
    assert CONFIDENCE == 0.95
    assert CHANCE == 0.5


def test_strong_oracle_is_judged_a_success() -> None:
    labels, scores = _separated(150, 2.0, 6)
    verdict = decide(labels, scores, rng_seed=1, n_resamples=600, n_permutations=600)
    assert verdict.attack_succeeds
    assert not verdict.at_chance
    assert verdict.auc >= AUC_SUCCESS_THRESHOLD


def test_hardened_result_is_judged_at_chance() -> None:
    labels, scores = _separated(150, 0.0, 6)
    verdict = decide(labels, scores, rng_seed=1, n_resamples=600, n_permutations=600)
    assert verdict.at_chance
    assert not verdict.attack_succeeds


def test_weak_oracle_is_neither_success_nor_at_chance() -> None:
    """The two flags are deliberately not complements.

    A real-but-weak signal must not be reportable as either a successful attack or
    a clean mitigation depending on which is convenient.
    """
    labels, scores = _separated(400, 0.5, 8)
    verdict = decide(labels, scores, rng_seed=1, n_resamples=600, n_permutations=600)
    assert not verdict.attack_succeeds
    assert not verdict.at_chance
    assert CHANCE < verdict.auc < AUC_SUCCESS_THRESHOLD


def test_verdict_is_reproducible_and_records_its_seed() -> None:
    labels, scores = _separated(60, 1.5, 2)
    kwargs = {"rng_seed": 99, "n_resamples": 400, "n_permutations": 400}
    first = decide(labels, scores, **kwargs)
    assert first == decide(labels, scores, **kwargs)
    assert first.seed == 99
    assert first.n == 120 and first.n_positive == 60 and first.n_negative == 60


def test_verdict_serialises_its_thresholds() -> None:
    """A published verdict must carry the bar it was judged against."""
    labels, scores = _separated(40, 1.5, 2)
    doc = decide(labels, scores, rng_seed=1, n_resamples=200, n_permutations=200).to_dict()
    assert doc["thresholds"] == {
        "auc_success": 0.75,
        "p_value": 0.01,
        "confidence": 0.95,
    }
    assert (
        "AUC=" in decide(labels, scores, rng_seed=1, n_resamples=200, n_permutations=200).summary()
    )


# --------------------------------------------------------------------------- noise


def test_noise_floor_summarises_dispersion() -> None:
    rng = np.random.default_rng(1)
    floor = measure_noise_floor(rng.normal(100.0, 5.0, 5000))
    assert floor.mean == pytest.approx(100.0, abs=0.5)
    assert floor.sd == pytest.approx(5.0, abs=0.5)
    assert floor.p50 < floor.p99
    assert floor.iqr > 0
    assert floor.n == 5000


def test_noise_floor_reports_iqr_as_well_as_sd() -> None:
    """One outlier should move SD far more than IQR — which is why both are kept."""
    clean = np.concatenate([np.full(999, 10.0), np.array([10.5])])
    spiked = np.concatenate([np.full(999, 10.0), np.array([10_000.0])])
    a, b = measure_noise_floor(clean), measure_noise_floor(spiked)
    assert b.sd > a.sd * 100
    assert b.iqr == pytest.approx(a.iqr, abs=1e-9)


def test_noise_floor_refuses_degenerate_input() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        measure_noise_floor(np.array([1.0]))
    with pytest.raises(ValueError, match="NaN"):
        measure_noise_floor(np.array([1.0, np.nan]))


def test_required_trials_scales_with_noise_and_effect() -> None:
    base = required_trials(noise_sd=10.0, effect=5.0)
    assert required_trials(noise_sd=20.0, effect=5.0) > base  # noisier -> more
    assert required_trials(noise_sd=10.0, effect=10.0) < base  # bigger effect -> fewer


def test_required_trials_matches_the_closed_form() -> None:
    """z_{0.975}=1.95996, z_{0.8}=0.84162 -> n = 2(2.80158)^2 = 15.7 -> 16."""
    assert required_trials(noise_sd=1.0, effect=1.0, power=0.8, alpha=0.05) == 16


def test_required_trials_refuses_nonsense() -> None:
    for kwargs in (
        {"noise_sd": 0.0, "effect": 1.0},
        {"noise_sd": 1.0, "effect": 0.0},
        {"noise_sd": 1.0, "effect": 1.0, "power": 1.5},
    ):
        with pytest.raises(ValueError):
            required_trials(**kwargs)


def test_required_trials_for_auc_decreases_as_the_effect_grows() -> None:
    assert required_trials_for_auc(0.6) > required_trials_for_auc(0.75)
    assert required_trials_for_auc(0.75) > required_trials_for_auc(0.9)


def test_required_trials_for_auc_at_the_pre_registered_bar_is_modest() -> None:
    """Sanity: the NFR-05 bar must be reachable at a trial count we can afford."""
    n = required_trials_for_auc(AUC_SUCCESS_THRESHOLD)
    assert 10 < n < 200


def test_required_trials_for_auc_refuses_chance_or_certainty() -> None:
    for bad in (0.5, 1.0, 0.2):
        with pytest.raises(ValueError):
            required_trials_for_auc(bad)
