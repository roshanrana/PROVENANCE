"""Noise floor and trial-count derivation.

NFR-04: trial counts for every timing claim are *derived from a measured baseline
variance*, and the derivation is committed. Picking a round number like "1000
trials" because it sounds thorough is exactly the kind of unexamined choice that
makes a benchmark unconvincing to the reader it is meant to persuade.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.stats import norm


@dataclass(frozen=True)
class NoiseFloor:
    """Baseline dispersion of a measurement, from repeated identical observations."""

    n: int
    mean: float
    sd: float
    p50: float
    p99: float
    #: Robust dispersion. Timing distributions have long right tails, and a single
    #: scheduler hiccup can double the SD while barely moving the IQR — so both are
    #: reported and the writeup says which one a given claim rests on.
    iqr: float

    def to_dict(self) -> dict[str, float | int]:
        return {
            "n": self.n,
            "mean": self.mean,
            "sd": self.sd,
            "p50": self.p50,
            "p99": self.p99,
            "iqr": self.iqr,
        }


def measure_noise_floor(samples: NDArray[np.float64]) -> NoiseFloor:
    """Summarise repeated measurements of a quantity that should not be varying."""
    arr = np.asarray(samples, dtype=np.float64)
    if arr.ndim != 1:
        raise ValueError(f"expected 1-D samples, got shape {arr.shape}")
    if arr.size < 2:
        raise ValueError(f"need at least 2 samples to estimate dispersion, got {arr.size}")
    if not np.all(np.isfinite(arr)):
        raise ValueError("samples contain NaN or infinity")

    q25, q75 = np.quantile(arr, [0.25, 0.75])
    return NoiseFloor(
        n=int(arr.size),
        mean=float(arr.mean()),
        sd=float(arr.std(ddof=1)),
        p50=float(np.quantile(arr, 0.5)),
        p99=float(np.quantile(arr, 0.99)),
        iqr=float(q75 - q25),
    )


def required_trials(
    noise_sd: float,
    effect: float,
    *,
    power: float = 0.8,
    alpha: float = 0.05,
) -> int:
    """Samples **per group** to detect a mean difference of *effect*.

    Normal-approximation two-sample formula:
    ``n = 2 (z_{1-alpha/2} + z_power)^2 * sd^2 / effect^2``.

    Assumes equal variance and independent samples. Both are approximations for
    latency data — it is heavy-tailed and successive requests are not fully
    independent — so this is a **floor**, a sanity check that a planned trial count
    is not absurdly small. It is not a substitute for reporting the confidence
    interval actually obtained, which is what NFR-05 requires.
    """
    if noise_sd <= 0:
        raise ValueError(f"noise_sd must be positive, got {noise_sd}")
    if effect <= 0:
        raise ValueError(f"effect must be positive, got {effect}")
    if not 0.0 < power < 1.0:
        raise ValueError(f"power must be in (0, 1), got {power}")
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")

    z_alpha = float(norm.ppf(1.0 - alpha / 2.0))
    z_power = float(norm.ppf(power))
    n = 2.0 * (z_alpha + z_power) ** 2 * noise_sd**2 / effect**2
    return max(2, math.ceil(n))


def required_trials_for_auc(
    target_auc: float,
    *,
    power: float = 0.8,
    alpha: float = 0.05,
    ratio: float = 1.0,
) -> int:
    """Positives needed to distinguish *target_auc* from chance (Hanley-McNeil).

    Used to sanity-check BARRIER's trial counts against the NFR-05 bar before the
    attack is run, rather than discovering afterwards that the sample was too small
    to have shown anything either way.
    """
    if not 0.5 < target_auc < 1.0:
        raise ValueError(f"target_auc must be in (0.5, 1.0), got {target_auc}")

    a = float(norm.ppf(target_auc) * math.sqrt(2.0))
    # Hanley & McNeil (1982) variance functions.
    q1 = a * math.exp(-(a**2) / 2.0) / math.sqrt(2.0 * math.pi)
    q2 = target_auc / (2.0 - target_auc)
    q3 = 2.0 * target_auc**2 / (1.0 + target_auc)

    var_null = 1.0 / 12.0 * (1.0 + 1.0 / ratio)
    var_alt = target_auc * (1.0 - target_auc) + (q2 - target_auc**2) + (q3 - target_auc**2) / ratio
    del q1  # part of the standard derivation, unused in this variance form

    z_alpha = float(norm.ppf(1.0 - alpha / 2.0))
    z_power = float(norm.ppf(power))
    numerator = (z_alpha * math.sqrt(var_null) + z_power * math.sqrt(var_alt)) ** 2
    n = numerator / (target_auc - 0.5) ** 2
    return max(2, math.ceil(n))
