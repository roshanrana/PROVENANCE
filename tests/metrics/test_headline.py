"""The headline document is observed, schema-valid, and not stale.

`metrics/headline.json` is what a results card renders. A tile that is wrong is
worse than a tile that is missing, so three things are enforced: the document
the harness builds matches the card schema exactly, the validator actually
rejects the ways a document can be wrong, and the committed file is what a fresh
build produces — the same drift rule `test_published_numbers.py` applies to prose.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from metrics.headline import (
    OUT,
    OVERVIEW,
    ROOT,
    HeadlineSchemaError,
    build_headline,
    component_paths,
    validate_headline,
)

Doc = dict[str, Any]


@pytest.fixture(scope="module")
def headline() -> Doc:
    """Built once per module: the coverage loop is the slow part."""
    return build_headline(ROOT)


def test_built_document_matches_the_schema(headline: Doc) -> None:
    validate_headline(headline)


def test_committed_file_is_what_a_fresh_build_produces(headline: Doc) -> None:
    assert OUT.is_file(), "run `make headline` (uv run python -m metrics.headline)"
    committed = json.loads(OUT.read_text(encoding="utf-8"))
    assert committed == headline, "metrics/headline.json is stale: run `make headline`"


def test_coverage_kpi_is_the_calibrated_number(headline: Doc) -> None:
    """The tile shows the same coverage the calibration test asserts on."""
    hits, trials = (headline["bars"]["rows"][0][k] for k in ("value", "max"))
    assert trials == 200
    assert headline["kpis"]["bootstrap_coverage"]["value"] == f"{hits / trials * 100:.1f}%"
    assert 0.88 <= hits / trials <= 0.99


def test_components_are_counted_from_the_manifest_and_exist(headline: Doc) -> None:
    paths = component_paths(ROOT)
    assert headline["kpis"]["components"]["value"] == str(len(paths))
    assert all((ROOT / p).is_dir() for p in paths)
    assert "common/stats" in paths
    assert "attest/receipt" in paths


def test_component_manifest_refuses_a_path_missing_from_the_tree(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="absent from the tree"):
        component_paths(tmp_path)


def test_facts_are_the_overview_table_verbatim(headline: Doc) -> None:
    overview = OVERVIEW.read_text(encoding="utf-8").replace("**", "")
    rows = headline["facts"]["rows"]
    assert len(rows) > 5
    for row in rows:
        assert row["label"] in overview
        evidence = row["value"].split(" [", 1)[0]
        assert evidence in overview


def test_rows_not_observed_offline_carry_a_reason(headline: Doc) -> None:
    statuses = {row["status"] for row in headline["facts"]["rows"]}
    assert "ok" in statuses and "pending" in statuses
    for row in headline["facts"]["rows"]:
        if row["status"] != "ok":
            assert f" [{row['status']}: " in row["value"], row["label"]


def _broken(doc: Doc, mutate: Callable[[Doc], Any]) -> Doc:
    clone = copy.deepcopy(doc)
    mutate(clone)
    return clone


def _over_max(d: Doc) -> None:
    d["bars"]["rows"][0]["value"] = d["bars"]["rows"][0]["max"] + 1


@pytest.mark.parametrize(
    ("what", "mutate"),
    [
        ("bad accent", lambda d: d["kpis"]["components"].update(accent="green")),
        ("bad status", lambda d: d["facts"]["rows"][0].update(status="done")),
        ("bar over max", _over_max),
        ("missing panel", lambda d: d.pop("facts")),
        ("extra kpi key", lambda d: d["kpis"]["components"].update(unit="n")),
        ("non-snake kpi key", lambda d: d["kpis"].update({"Bad-Key": d["kpis"]["components"]})),
        ("bool bar value", lambda d: d["bars"]["rows"][0].update(value=True)),
    ],
)
def test_validator_rejects(headline: Doc, what: str, mutate: Callable[[Doc], Any]) -> None:
    with pytest.raises(HeadlineSchemaError):
        validate_headline(_broken(headline, mutate))
