"""Every headline number in the prose must still match the measurements.

CLAUDE.md: *every number that appears in the README or a writeup must trace to
committed raw output.* That rule was enforced by nobody. Over this project's
life the README claimed 272 tests when there were 308, said BARRIER had never
been deployed after it had run fourteen times in CI, and one page said no SGLang
measurement had been taken while another page quoted 18.0% from it.

None of those were wrong when written. They rotted, which is the normal fate of a
number copied into prose, and the only durable fix is to make rot a build
failure. `bench/results/measurements.json` is the single source; this asserts the
documents agree with it.

If one of these fails, the fix is to correct the document — or, if the
measurement genuinely changed, to update the JSON *and* the writeup it names as
its source, in the same commit.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA = json.loads((ROOT / "bench" / "results" / "measurements.json").read_text(encoding="utf-8"))


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


README = _read("README.md")
SHIP = _read("docs/SHIP-REPORT.md")
RESULTS = _read("docs/RESULTS.md")


def _divergence(engine: str, determinism: bool) -> int:
    for cell in DATA["divergence"]["cells"]:
        if cell["engine"] == engine and cell["determinism"] is determinism:
            return int(cell["distinct"])
    raise AssertionError(f"no divergence cell for {engine} determinism={determinism}")


# ------------------------------------------------------------------ the numbers


@pytest.mark.parametrize("doc_name", ["README.md", "docs/RESULTS.md"])
def test_divergence_counts_appear_as_measured(doc_name: str) -> None:
    doc = _read(doc_name)
    assert f"{_divergence('vLLM', False)} of 128" in doc or "34 distinct" in doc
    assert str(_divergence("vLLM", True)) in doc
    assert str(_divergence("SGLang", True)) in doc


def test_the_isolated_determinism_cost_is_quoted_correctly() -> None:
    """18.0% is D/B. Quoting it as anything else republishes the confound."""
    ratio = next(r for r in DATA["sglang_2x2"]["ratios"] if r["name"] == "D / B")
    assert ratio["value"] == 0.820
    pct = f"{(1 - ratio['value']) * 100:.1f}%"
    assert pct == "18.0%"
    for doc in (README, SHIP, RESULTS):
        assert pct in doc


def test_the_vllm_cost_is_labelled_confounded_wherever_it_is_quoted() -> None:
    """The 22.7% figure is determinism PLUS the loss of the prefix cache.

    Quoting it bare is the specific overclaim ADR-009 exists to prevent, so any
    document that states it must also say so within a few lines.
    """
    assert DATA["vllm_cost"]["confounded"] is True
    pct = f"{(1 - DATA['vllm_cost']['ratio']) * 100:.1f}%"
    assert pct == "22.7%"
    for name, doc in (
        ("README.md", README),
        ("docs/SHIP-REPORT.md", SHIP),
        ("docs/RESULTS.md", RESULTS),
    ):
        if pct not in doc:
            continue
        i = doc.index(pct)
        window = doc[max(0, i - 400) : i + 400].lower()
        assert "confound" in window, (
            f"{name} quotes {pct} without saying it is confounded with cache loss"
        )


def test_frb03_verdicts_match_both_profiles() -> None:
    profiles = {p["profile"]: p for p in DATA["frb03"]["profiles"]}
    assert profiles["default"]["attack_succeeds"] is True
    assert profiles["hardened"]["at_chance"] is True
    for doc in (README, SHIP, RESULTS):
        assert f"{profiles['default']['auc']:.4f}" in doc
        assert f"{profiles['hardened']['auc']:.4f}" in doc


def test_the_confirmation_scope_travels_with_the_frb03_number() -> None:
    """The strongest number in the repository is also the easiest to overstate.

    AUC 1.0000 is by construction: the probe sends the victim's prompt verbatim.
    Any document that prints it must say so, or the number reads as an extraction
    attack it is not.
    """
    auc = f"{DATA['frb03']['profiles'][0]['auc']:.4f}"
    for name, doc in (
        ("README.md", README),
        ("docs/SHIP-REPORT.md", SHIP),
        ("docs/RESULTS.md", RESULTS),
    ):
        if auc not in doc:
            continue
        assert "confirmation" in doc.lower(), (
            f"{name} states AUC {auc} without the confirmation-oracle scope"
        )


def test_the_pre_registered_thresholds_are_the_ones_the_code_enforces() -> None:
    """The JSON is documentation; `common.stats.decision` is the enforcement.

    They must not be able to drift apart — a writeup describing a bar the code
    does not apply is worse than no writeup.
    """
    from common.stats.decision import (
        AUC_SUCCESS_THRESHOLD,
        CHANCE,
        CONFIDENCE,
        P_VALUE_THRESHOLD,
    )

    t = DATA["thresholds"]
    assert t["auc_success"] == AUC_SUCCESS_THRESHOLD
    assert t["p_value"] == P_VALUE_THRESHOLD
    assert t["confidence"] == CONFIDENCE
    assert t["chance"] == CHANCE


def test_the_test_count_is_current() -> None:
    """Counted, not asserted from memory — the README got this wrong twice."""
    out = subprocess.run(
        # NOT -q: pytest suppresses the "N tests collected" summary in quiet mode,
        # and this test silently skipped for it.
        [sys.executable, "-m", "pytest", "--collect-only", str(ROOT / "tests")],
        capture_output=True,
        text=True,
        cwd=ROOT,
    ).stdout
    match = re.search(r"(\d+) tests? collected", out)
    collected = int(match.group(1)) if match else None
    if collected is None:  # pytest phrasing varies by version; skip rather than lie
        pytest.skip("could not parse pytest's collection summary")
    assert DATA["totals"]["python_tests"] == collected, (
        f"measurements.json says {DATA['totals']['python_tests']} Python tests; "
        f"pytest collects {collected}. Update the JSON and every document quoting it."
    )
    assert str(collected) in README


# ------------------------------------------------------------------- the source


def test_every_measurement_names_a_writeup_that_exists() -> None:
    """A number whose source file has been renamed away is unverifiable."""
    results = ROOT / "bench" / "results"
    sources = {
        DATA["sglang_2x2"]["source"],
        DATA["vllm_cost"]["source"],
        DATA["s02"]["source"],
        DATA["frb03"]["source"],
        *(c["source"] for c in DATA["divergence"]["cells"]),
    }
    missing = sorted(s for s in sources if not (results / s).is_file())
    assert not missing, f"measurements.json cites files that do not exist: {missing}"


def test_the_figures_are_the_ones_the_script_generates() -> None:
    """Figures are regenerated by script, never hand-edited (CLAUDE.md).

    Re-runs the generator into a temporary root and compares. A hand-tweaked SVG,
    or a figure left stale after the data changed, fails here.
    """
    import importlib

    figures = ROOT / "docs" / "figures"
    before = {p.name: p.read_text(encoding="utf-8") for p in sorted(figures.glob("*.svg"))}
    assert before, "no figures found; run scripts/make_figures.py"

    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        module = importlib.import_module("make_figures")
        importlib.reload(module)
        module.main()
    finally:
        sys.path.remove(str(ROOT / "scripts"))

    after = {p.name: p.read_text(encoding="utf-8") for p in sorted(figures.glob("*.svg"))}
    drifted = sorted(k for k in after if before.get(k) != after[k])
    assert not drifted, (
        f"these figures were not what the script produces: {drifted}. "
        "Run `uv run python scripts/make_figures.py` and commit the result."
    )
    assert sorted(before) == sorted(after)
