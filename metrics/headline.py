"""Write ``metrics/headline.json``: the numbers a results card may show.

Three sources, all observed by this process, none typed in:

* **Bootstrap coverage** — ``common.stats.calibration.bootstrap_coverage`` with the
  same seeds the calibration test uses, so the published figure is the tested one.
* **Components** — the manifest in ``docs/design/02-hld.md`` §4, each path checked
  to exist on the tree. Counted, not asserted.
* **Facts** — the "demonstrated, and what has not" table in ``docs/OVERVIEW.md``,
  row for row. Rows demonstrable with no GPU are ``ok``; rows whose evidence needs a
  GPU or a cluster are ``pending`` with the reason, because this harness did not
  observe them and must not pretend it did.

Offline, seeded, no network. The document is validated against the card schema
before it is written; an invalid document is a defect, not a file.

    uv run python -m metrics.headline
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from common.stats.calibration import CoverageResult, bootstrap_coverage

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "metrics" / "headline.json"
HLD = ROOT / "docs" / "design" / "02-hld.md"
OVERVIEW = ROOT / "docs" / "OVERVIEW.md"

COMPONENTS_HEADING = "## 4. Components"
FACTS_HEADING = "## What has been demonstrated, and what has not"

ACCENTS = frozenset({"teal", "blue", "amber", "violet", "red"})
STATUSES = frozenset({"ok", "pending", "blocked"})
KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# The OVERVIEW table's own status vocabulary, mapped to what this harness can
# vouch for. Anything not listed is an unknown claim type and fails loudly.
_STATUS_RULES: tuple[tuple[str, str, str], ...] = (
    ("Demonstrated", "ok", ""),
    (
        "Measured",
        "pending",
        "needs a GPU or the CI kind cluster; recorded in bench/results, "
        "not re-observed by this offline harness",
    ),
    ("Stood up on every push", "pending", "needs Docker + kind; runs in the BARRIER CI workflow"),
    ("Open", "pending", "FR-B-09 is open: needs real vLLM on a GPU"),
    ("Not claimed", "blocked", "not claimed by design"),
)


class HeadlineSchemaError(ValueError):
    """The document does not match the card schema."""


# --------------------------------------------------------------------------- parsing


def _section(text: str, heading: str, path: Path) -> str:
    start = text.find(heading)
    if start < 0:
        raise ValueError(f"{path.name}: heading not found: {heading!r}")
    body = text[start + len(heading) :]
    end = body.find("\n## ")
    return body if end < 0 else body[:end]


def _table_rows(section: str) -> list[list[str]]:
    """Body rows of the first markdown table in ``section``, cells stripped of bold."""
    rows: list[list[str]] = []
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip().replace("**", "") for c in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r"-+", c) for c in cells):
            continue
        rows.append(cells)
    if len(rows) < 2:
        raise ValueError("no markdown table with body rows found")
    return rows[1:]


def component_paths(root: Path = ROOT) -> list[str]:
    """Paths of the components the HLD declares, each verified to exist."""
    rows = _table_rows(_section(HLD.read_text(encoding="utf-8"), COMPONENTS_HEADING, HLD))
    paths = [r[1].strip("`").rstrip("/") for r in rows if re.fullmatch(r"C\d+", r[0])]
    if not paths:
        raise ValueError(f"{HLD.name}: no C# rows under {COMPONENTS_HEADING!r}")
    missing = [p for p in paths if not (root / p).is_dir()]
    if missing:
        raise ValueError(f"{HLD.name} lists components absent from the tree: {missing}")
    return paths


def _fact_row(claim: str, doc_status: str, evidence: str) -> dict[str, str]:
    for prefix, status, reason in _STATUS_RULES:
        if doc_status.startswith(prefix):
            value = evidence if not reason else f"{evidence} [{status}: {reason}]"
            return {"label": claim, "value": value, "status": status}
    raise ValueError(f"{OVERVIEW.name}: unrecognised status {doc_status!r} for {claim!r}")


def fact_rows() -> list[dict[str, str]]:
    """The OVERVIEW claims table, verbatim, with a harness-assigned status."""
    rows = _table_rows(_section(OVERVIEW.read_text(encoding="utf-8"), FACTS_HEADING, OVERVIEW))
    return [_fact_row(*r[:3]) for r in rows]


# --------------------------------------------------------------------------- build


def _coverage_kpi(cov: CoverageResult) -> dict[str, str]:
    return {
        "label": "Bootstrap CI coverage",
        "value": f"{cov.coverage * 100:.1f}%",
        "note": (
            f"{cov.trials} null datasets, nominal {cov.nominal:.0%}; "
            f"n={2 * cov.n_per_class}, {cov.n_resamples} resamples, seeds {cov.seed_base}+"
        ),
        "accent": "teal",
    }


def build_headline(root: Path = ROOT) -> dict[str, Any]:
    """Assemble the document from observed values only."""
    cov = bootstrap_coverage()
    components = component_paths(root)
    facts = fact_rows()
    offline = sum(1 for f in facts if f["status"] == "ok")
    return {
        "kpis": {
            "bootstrap_coverage": _coverage_kpi(cov),
            "components": {
                "label": "Components",
                "value": str(len(components)),
                "note": "declared in docs/design/02-hld.md §4; every path present on the tree",
                "accent": "blue",
            },
        },
        "bars": {
            "title": "Observed offline",
            "rows": [
                {
                    "label": "Null datasets whose 95% CI contained 0.5",
                    "value": cov.hits,
                    "max": cov.trials,
                    "display": f"{cov.hits}/{cov.trials}",
                    "accent": "teal",
                },
                {
                    "label": "Claims verifiable with no GPU",
                    "value": offline,
                    "max": len(facts),
                    "display": f"{offline}/{len(facts)}",
                    "accent": "blue",
                },
            ],
        },
        "facts": {"title": "What has been demonstrated, and what has not", "rows": facts},
    }


# --------------------------------------------------------------------------- schema


def _require(cond: bool, where: str, msg: str) -> None:
    if not cond:
        raise HeadlineSchemaError(f"{where}: {msg}")


def _check_keys(obj: Any, expected: set[str], where: str) -> None:
    _require(isinstance(obj, dict), where, "must be an object")
    _require(set(obj) == expected, where, f"keys must be exactly {sorted(expected)}")


def _check_strings(obj: dict[str, Any], keys: tuple[str, ...], where: str) -> None:
    for k in keys:
        _require(isinstance(obj[k], str) and obj[k] != "", f"{where}.{k}", "must be a string")


def _is_number(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


def _check_kpis(kpis: Any) -> None:
    _require(isinstance(kpis, dict), "kpis", "must be an object")
    for key, kpi in kpis.items():
        where = f"kpis.{key}"
        _require(bool(KEY_RE.match(key)), where, "key must be snake_case")
        _check_keys(kpi, {"label", "value", "note", "accent"}, where)
        _check_strings(kpi, ("label", "value", "note"), where)
        _require(kpi["accent"] in ACCENTS, f"{where}.accent", f"must be one of {sorted(ACCENTS)}")


def _check_bars(bars: Any) -> None:
    _check_keys(bars, {"title", "rows"}, "bars")
    _check_strings(bars, ("title",), "bars")
    _require(isinstance(bars["rows"], list), "bars.rows", "must be a list")
    for i, row in enumerate(bars["rows"]):
        where = f"bars.rows[{i}]"
        _check_keys(row, {"label", "value", "max", "display", "accent"}, where)
        _check_strings(row, ("label", "display"), where)
        _require(_is_number(row["value"]) and _is_number(row["max"]), where, "value/max numeric")
        _require(row["max"] > 0, f"{where}.max", "must be positive")
        _require(0 <= row["value"] <= row["max"], f"{where}.value", "must be within [0, max]")
        _require(row["accent"] in ACCENTS, f"{where}.accent", f"must be one of {sorted(ACCENTS)}")


def _check_facts(facts: Any) -> None:
    _check_keys(facts, {"title", "rows"}, "facts")
    _check_strings(facts, ("title",), "facts")
    _require(isinstance(facts["rows"], list), "facts.rows", "must be a list")
    for i, row in enumerate(facts["rows"]):
        where = f"facts.rows[{i}]"
        _check_keys(row, {"label", "value", "status"}, where)
        _check_strings(row, ("label", "value"), where)
        _require(row["status"] in STATUSES, f"{where}.status", f"must be one of {sorted(STATUSES)}")


def validate_headline(doc: Any) -> None:
    """Raise ``HeadlineSchemaError`` unless ``doc`` matches the card schema exactly."""
    _check_keys(doc, {"kpis", "bars", "facts"}, "headline")
    _check_kpis(doc["kpis"])
    _check_bars(doc["bars"])
    _check_facts(doc["facts"])


# --------------------------------------------------------------------------- entry


def main() -> int:
    doc = build_headline()
    validate_headline(doc)
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    coverage = doc["kpis"]["bootstrap_coverage"]["value"]
    components = doc["kpis"]["components"]["value"]
    print(f"wrote {OUT.relative_to(ROOT)}: coverage {coverage}, {components} components")
    return 0


if __name__ == "__main__":
    sys.exit(main())
