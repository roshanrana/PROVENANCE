"""The positive control for S-02's negative result.

If these are wrong, a misconfigured cluster gets published as a security
property. That is the most expensive mistake available to this project, so the
gate is tested against the exact exposition shapes the EPP emits.
"""

from __future__ import annotations

from pathlib import Path

from barrier.attack.ground_truth import main, read_ground_truth

# Trimmed from the real dump in BARRIER CI run #10, both published families kept.
# ruff: noqa: E501  — verbatim Prometheus exposition; rewrapping it would stop it
# being the thing the EPP actually emits, which is the point of the fixture.
_REAL_SHAPE = """\
# HELP inference_extension_plugin_duration_seconds [ALPHA] Plugin duration
# TYPE inference_extension_plugin_duration_seconds histogram
inference_extension_plugin_duration_seconds_bucket{plugin_name="approx-prefix-cache-producer",le="0.0001"} 64
inference_extension_plugin_duration_seconds_count{plugin_name="approx-prefix-cache-producer"} 64
# TYPE inference_extension_prefix_indexer_hit_ratio histogram
inference_extension_prefix_indexer_hit_ratio_bucket{le="0"} 40
inference_extension_prefix_indexer_hit_ratio_bucket{le="0.5"} 55
inference_extension_prefix_indexer_hit_ratio_bucket{le="+Inf"} 64
inference_extension_prefix_indexer_hit_ratio_count 64
# TYPE llm_d_router_epp_prefix_indexer_size gauge
llm_d_router_epp_prefix_indexer_size{plugin_name="approx-prefix-cache-producer"} 12
"""


def test_the_plugin_duration_metric_alone_does_not_satisfy_the_control() -> None:
    """F-26: the first gate passed on exactly this and proved nothing.

    `plugin_duration_seconds{plugin_name="approx-prefix-cache-producer"}` shows a
    plugin by that name executed. It says nothing about whether the index ever
    matched, which is the only fact the control needs.
    """
    only_duration = "\n".join(_REAL_SHAPE.splitlines()[:4])
    truth = read_ground_truth(only_duration)
    assert truth.lookups == 0
    assert truth.holds is False
    assert "NEVER CONSULTED" in truth.summary()


def test_a_real_dump_with_matches_satisfies_the_control() -> None:
    truth = read_ground_truth(_REAL_SHAPE)
    assert truth.lookups == 64
    assert truth.matched_nothing == 40
    assert truth.matched_something == 24
    assert truth.index_size == 12
    assert truth.holds is True


def test_every_lookup_matching_nothing_fails_the_control() -> None:
    """The dangerous case: the index is consulted and never matches.

    A client-side spike sees no signal, and it is right — there was nothing to
    signal. Publishing that as 'no leak' would be a false negative dressed as a
    finding.
    """
    dump = _REAL_SHAPE.replace(
        'inference_extension_prefix_indexer_hit_ratio_bucket{le="0"} 40',
        'inference_extension_prefix_indexer_hit_ratio_bucket{le="0"} 64',
    )
    truth = read_ground_truth(dump)
    assert truth.lookups == 64
    assert truth.matched_something == 0
    assert truth.holds is False


def test_an_upstream_rename_does_not_disarm_the_gate() -> None:
    """Only the llm_d_router_epp family is present — the deprecated one is gone."""
    dump = """\
llm_d_router_epp_prefix_indexer_hit_ratio_bucket{plugin_name="p",le="0"} 5
llm_d_router_epp_prefix_indexer_hit_ratio_count{plugin_name="p"} 20
"""
    truth = read_ground_truth(dump)
    assert truth.lookups == 20
    assert truth.matched_something == 15
    assert truth.holds is True


def test_zero_bucket_written_as_a_decimal_is_still_the_zero_bucket() -> None:
    dump = """\
prefix_indexer_hit_ratio_bucket{le="0.0"} 3
prefix_indexer_hit_ratio_count 3
"""
    assert read_ground_truth(dump).holds is False


def test_cli_exits_5_when_the_control_fails(tmp_path: Path) -> None:
    path = tmp_path / "metrics.txt"
    path.write_text("prefix_indexer_hit_ratio_count 0\n", encoding="utf-8")
    assert main([str(path)]) == 5


def test_cli_exits_5_when_the_dump_is_missing(tmp_path: Path) -> None:
    assert main([str(tmp_path / "nope.txt")]) == 5


def test_cli_exits_0_when_the_control_holds(tmp_path: Path) -> None:
    path = tmp_path / "metrics.txt"
    path.write_text(_REAL_SHAPE, encoding="utf-8")
    assert main([str(path)]) == 0
