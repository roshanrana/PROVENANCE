from __future__ import annotations

import numpy as np
import pytest

from attest.analysis.cost import (
    IncomparableMeasurements,
    build_cost_report,
    ratio_bootstrap_ci,
    summarise_latency,
)

CONDITIONS = {
    "gpu": "L4",
    "model": "Qwen/Qwen2.5-0.5B-Instruct",
    "run_id": "attest-20260829T000000Z-abc1234",
    "max_tokens": 256,
    "concurrency": 16,
}


def _samples(mean: float, sd: float, n: int, seed: int) -> np.ndarray:
    return np.abs(np.random.default_rng(seed).normal(mean, sd, n))


# --------------------------------------------------------------------------- summaries


def test_latency_summary_reports_tail_percentiles() -> None:
    """A mean hides exactly the behaviour an operator cares about."""
    summary = summarise_latency(np.concatenate([np.full(99, 10.0), np.array([1000.0])]))
    assert summary.p50 == pytest.approx(10.0)
    assert summary.p99 > summary.p95 >= summary.p50
    assert summary.mean > summary.p50  # the tail drags the mean


def test_empty_samples_are_refused() -> None:
    with pytest.raises(ValueError, match="no latency samples"):
        summarise_latency([])


def test_negative_latency_is_refused() -> None:
    """Negative latency is not a measurement; it is a bug upstream."""
    with pytest.raises(ValueError, match="negative latency"):
        summarise_latency([1.0, -0.5])


def test_non_finite_latency_is_refused() -> None:
    with pytest.raises(ValueError, match="NaN"):
        summarise_latency([1.0, np.inf])


# --------------------------------------------------------------------------- ratios


def test_ratio_recovers_a_known_slowdown() -> None:
    base = _samples(100.0, 1.0, 500, 1)
    treat = _samples(70.0, 1.0, 500, 2)
    point, lo, hi = ratio_bootstrap_ci(base, treat, n_resamples=400, rng_seed=3)
    assert point == pytest.approx(0.7, abs=0.02)
    assert lo < point < hi


def test_ratio_interval_contains_one_when_arms_are_identical() -> None:
    base = _samples(100.0, 10.0, 400, 1)
    treat = _samples(100.0, 10.0, 400, 2)
    _, lo, hi = ratio_bootstrap_ci(base, treat, n_resamples=400, rng_seed=3)
    assert lo <= 1.0 <= hi


def test_ratio_is_deterministic_for_a_fixed_seed() -> None:
    base, treat = _samples(100.0, 5.0, 100, 1), _samples(80.0, 5.0, 100, 2)
    first = ratio_bootstrap_ci(base, treat, n_resamples=200, rng_seed=7)
    second = ratio_bootstrap_ci(base, treat, n_resamples=200, rng_seed=7)
    assert first == second


def test_percentile_statistic_is_supported() -> None:
    base, treat = _samples(100.0, 20.0, 300, 1), _samples(150.0, 20.0, 300, 2)
    point, _, _ = ratio_bootstrap_ci(base, treat, statistic="p99", n_resamples=200, rng_seed=1)
    assert point > 1.0


def test_unknown_statistic_is_refused() -> None:
    base, treat = _samples(100.0, 5.0, 10, 1), _samples(100.0, 5.0, 10, 2)
    with pytest.raises(ValueError, match="unknown statistic"):
        ratio_bootstrap_ci(base, treat, statistic="median", n_resamples=10, rng_seed=1)


def test_too_few_samples_are_refused() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        ratio_bootstrap_ci(np.array([1.0]), np.array([1.0, 2.0]), n_resamples=10, rng_seed=1)


# --------------------------------------------------------------------------- report


def _report(**over: object) -> object:
    kwargs = dict(
        throughput_off=_samples(1000.0, 30.0, 200, 1),
        throughput_on=_samples(700.0, 30.0, 200, 2),
        ttft_off=_samples(50.0, 8.0, 200, 3),
        ttft_on=_samples(65.0, 10.0, 200, 4),
        conditions_off=CONDITIONS,
        conditions_on=CONDITIONS,
        rng_seed=11,
        n_resamples=300,
    )
    kwargs.update(over)
    return build_cost_report(**kwargs)  # type: ignore[arg-type]


def test_report_quantifies_the_cost_with_intervals() -> None:
    report = _report()
    point, lo, hi = report.throughput_ratio  # type: ignore[attr-defined]
    assert point == pytest.approx(0.7, abs=0.03)
    assert lo < point < hi
    assert "costs" in report.headline()  # type: ignore[attr-defined]
    assert "95% CI" in report.headline()  # type: ignore[attr-defined]


def test_report_renders_a_table_with_ci_columns() -> None:
    table = _report().to_markdown()  # type: ignore[attr-defined]
    assert "95% CI" in table
    assert table.count("\n") == 4  # header + separator + 3 metric rows
    assert "TTFT p99" in table


def test_report_serialises_its_conditions_and_seed() -> None:
    doc = _report().to_dict()  # type: ignore[attr-defined]
    assert doc["seed"] == 11
    assert doc["conditions"]["gpu"] == "L4"
    assert len(doc["throughput_ratio"]) == 3


def test_mismatched_hardware_is_refused() -> None:
    """Throughput measured on two machines is not a delta, it is two numbers."""
    with pytest.raises(IncomparableMeasurements, match="gpu"):
        _report(conditions_on={**CONDITIONS, "gpu": "A100"})


def test_mismatched_model_is_refused() -> None:
    with pytest.raises(IncomparableMeasurements, match="model"):
        _report(conditions_on={**CONDITIONS, "model": "Qwen/Qwen2.5-7B-Instruct"})


def test_mismatched_session_is_refused() -> None:
    """Two arms from different runs did not share thermal or scheduling conditions."""
    with pytest.raises(IncomparableMeasurements, match="run_id"):
        _report(conditions_on={**CONDITIONS, "run_id": "attest-20260830T000000Z-def5678"})


def test_a_speedup_is_reported_as_a_gain_not_forced_into_a_cost() -> None:
    """If invariance turned out to be faster, the report must say so."""
    report = _report(
        throughput_off=_samples(700.0, 20.0, 200, 1),
        throughput_on=_samples(1000.0, 20.0, 200, 2),
    )
    assert "gains" in report.headline()  # type: ignore[attr-defined]
