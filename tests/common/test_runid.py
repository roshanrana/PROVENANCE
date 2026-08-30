from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime, timezone
from pathlib import Path

import pytest

from common.runid import (
    RUN_ID_RE,
    Manifest,
    NotAGitRepositoryError,
    git_state,
    iso,
    new_run_id,
)

FIXED = datetime(2026, 8, 29, 14, 30, 5, tzinfo=UTC)


def _init_repo(path: Path, *, dirty: bool = False) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=path, check=True)
    (path / "seed.txt").write_text("seed\n")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=path, check=True)
    if dirty:
        (path / "seed.txt").write_text("changed\n")


# --------------------------------------------------------------------------- run ids


def test_run_id_is_deterministic_given_now_and_sha() -> None:
    a = new_run_id("attest", now=FIXED, git_sha="abc1234")
    b = new_run_id("attest", now=FIXED, git_sha="abc1234")
    assert a == b == "attest-20260829T143005Z-abc1234"


def test_run_id_matches_frozen_format() -> None:
    assert RUN_ID_RE.match(new_run_id("barrier", now=FIXED, git_sha="0f9e8d7"))


def test_run_id_rejects_a_malformed_sha() -> None:
    # A non-hex or wrong-length SHA must fail loudly rather than produce a run-id
    # that no longer encodes usable provenance.
    with pytest.raises(ValueError):
        new_run_id("attest", now=FIXED, git_sha="nothex!")


def test_run_id_normalises_a_non_utc_now() -> None:
    from datetime import timedelta

    non_utc = FIXED.astimezone(timezone(timedelta(hours=5)))
    assert new_run_id("attest", now=non_utc, git_sha="abc1234") == (
        "attest-20260829T143005Z-abc1234"
    )


# --------------------------------------------------------------------------- git state


def test_git_state_reports_clean_tree(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    sha, dirty = git_state(tmp_path)
    assert len(sha) == 7 and not dirty


def test_dirty_tree_is_recorded_not_raised(tmp_path: Path) -> None:
    _init_repo(tmp_path, dirty=True)
    _, dirty = git_state(tmp_path)
    assert dirty is True


def test_outside_a_repo_raises_typed_error(tmp_path: Path) -> None:
    outside = tmp_path / "plain"
    outside.mkdir()
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(tmp_path))
    prev = os.environ.copy()
    os.environ.update(env)
    try:
        with pytest.raises(NotAGitRepositoryError):
            git_state(outside)
    finally:
        os.environ.clear()
        os.environ.update(prev)


# --------------------------------------------------------------------------- manifest


def _manifest() -> Manifest:
    return Manifest.start(
        "attest",
        command="uv run attest-run --stage 1",
        now=FIXED,
        git=("abc1234", False),
        environment={"gpu": "L4", "python": "3.12.11"},
    )


def test_manifest_round_trips_without_field_loss() -> None:
    m = _manifest().finalize(cells_total=4, cells_done=3, cells_failed=1, now=FIXED)
    assert Manifest.from_dict(m.to_dict()) == m


def test_manifest_records_dirty_flag() -> None:
    m = Manifest.start("barrier", command="x", now=FIXED, git=("abc1234", True))
    assert m.git_dirty is True and m.to_dict()["git_dirty"] is True


def test_manifest_rejects_missing_required_field() -> None:
    doc = _manifest().to_dict()
    del doc["git_sha"]
    with pytest.raises(ValueError, match="git_sha"):
        Manifest.from_dict(doc)


def test_manifest_rejects_unknown_workstream() -> None:
    doc = _manifest().to_dict()
    doc["workstream"] = "elsewhere"
    with pytest.raises(ValueError, match="workstream"):
        Manifest.from_dict(doc)


def test_write_is_atomic_and_leaves_no_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the replace step fails, the target must not exist and no temp file may survive.

    A half-written manifest is worse than none: it looks like evidence.
    """
    target = tmp_path / "run" / "manifest.json"

    def boom(*_a: object, **_k: object) -> None:
        raise OSError("simulated interruption")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        _manifest().write(target)

    assert not target.exists()
    assert list(target.parent.glob(".manifest-*.tmp")) == []


def test_write_then_read(tmp_path: Path) -> None:
    target = tmp_path / "run" / "manifest.json"
    m = _manifest().finalize(cells_total=1, cells_done=1, cells_failed=0, now=FIXED)
    m.write(target)
    assert Manifest.read(target) == m
    assert json.loads(target.read_text())["run_id"] == m.run_id


def test_iso_is_seconds_precision_utc() -> None:
    assert iso(FIXED.replace(microsecond=123456)) == "2026-08-29T14:30:05Z"
