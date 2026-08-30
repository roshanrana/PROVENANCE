"""Run identity and manifest construction.

This module is what makes NFR-01 true by construction rather than by discipline:
every published number must trace to committed raw output plus the exact command
and git SHA that produced it. A ``run-id`` carries that provenance in its name, and
the manifest carries the rest.

Contracts are frozen at LLD §4.5.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

Workstream = Literal["attest", "barrier"]

#: ``<workstream>-<YYYYMMDDTHHMMSSZ>-<7 hex>`` — provenance legible from the path alone.
RUN_ID_RE = re.compile(r"^(attest|barrier)-\d{8}T\d{6}Z-[0-9a-f]{7}$")

_TIMESTAMP_FMT = "%Y%m%dT%H%M%SZ"


class NotAGitRepositoryError(RuntimeError):
    """Raised when git state is requested outside a git repository.

    A typed error, not a sentinel: a run whose git SHA silently became ``None``
    would produce output that cannot be traced back to the code that made it,
    which is the one thing NFR-01 exists to prevent.
    """


def git_state(cwd: Path | None = None) -> tuple[str, bool]:
    """Return ``(short_sha, dirty)`` for the repository containing *cwd*.

    A dirty tree is **recorded, not rejected**. Development runs happen on dirty
    trees; pretending otherwise is how an untraceable number gets published.
    """
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short=7", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise NotAGitRepositoryError(
            f"not a git repository (or git unavailable): {cwd or Path.cwd()}"
        ) from exc
    return sha, bool(status.strip())


def utc_now() -> datetime:
    """Current UTC time, seconds precision. Injectable seam for tests (NFR-03)."""
    return datetime.now(UTC).replace(microsecond=0)


def new_run_id(
    workstream: Workstream,
    *,
    now: datetime | None = None,
    git_sha: str | None = None,
    cwd: Path | None = None,
) -> str:
    """Build a run-id. Pure given *now* and *git_sha*."""
    stamp = (now or utc_now()).astimezone(UTC).strftime(_TIMESTAMP_FMT)
    sha = git_sha if git_sha is not None else git_state(cwd)[0]
    run_id = f"{workstream}-{stamp}-{sha}"
    if not RUN_ID_RE.match(run_id):
        raise ValueError(f"constructed run_id does not match the frozen format: {run_id!r}")
    return run_id


def iso(ts: datetime) -> str:
    """UTC, ISO-8601, seconds precision, ``Z`` suffix."""
    return ts.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class Manifest:
    """The run manifest. Schema frozen at LLD §4.5."""

    run_id: str
    workstream: Workstream
    command: str
    git_sha: str
    git_dirty: bool
    started_utc: str
    finished_utc: str | None = None
    environment: Mapping[str, Any] | None = None
    cells_total: int = 0
    cells_done: int = 0
    cells_failed: int = 0

    @classmethod
    def start(
        cls,
        workstream: Workstream,
        *,
        command: str,
        now: datetime | None = None,
        environment: Mapping[str, Any] | None = None,
        cwd: Path | None = None,
        git: tuple[str, bool] | None = None,
    ) -> Manifest:
        started = now or utc_now()
        sha, dirty = git if git is not None else git_state(cwd)
        return cls(
            run_id=new_run_id(workstream, now=started, git_sha=sha),
            workstream=workstream,
            command=command,
            git_sha=sha,
            git_dirty=dirty,
            started_utc=iso(started),
            environment=dict(environment) if environment is not None else {},
        )

    def finalize(
        self,
        *,
        cells_total: int,
        cells_done: int,
        cells_failed: int,
        now: datetime | None = None,
    ) -> Manifest:
        return replace(
            self,
            finished_utc=iso(now or utc_now()),
            cells_total=cells_total,
            cells_done=cells_done,
            cells_failed=cells_failed,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "workstream": self.workstream,
            "command": self.command,
            "git_sha": self.git_sha,
            "git_dirty": self.git_dirty,
            "started_utc": self.started_utc,
            "finished_utc": self.finished_utc,
            "environment": dict(self.environment) if self.environment is not None else {},
            "cells_total": self.cells_total,
            "cells_done": self.cells_done,
            "cells_failed": self.cells_failed,
        }

    @classmethod
    def from_dict(cls, doc: Mapping[str, Any]) -> Manifest:
        required = {"run_id", "workstream", "command", "git_sha", "git_dirty", "started_utc"}
        missing = required - set(doc)
        if missing:
            raise ValueError(f"manifest missing required field(s): {sorted(missing)}")
        workstream = doc["workstream"]
        if workstream not in ("attest", "barrier"):
            raise ValueError(f"unknown workstream: {workstream!r}")
        return cls(
            run_id=doc["run_id"],
            workstream=workstream,
            command=doc["command"],
            git_sha=doc["git_sha"],
            git_dirty=bool(doc["git_dirty"]),
            started_utc=doc["started_utc"],
            finished_utc=doc.get("finished_utc"),
            environment=doc.get("environment") or {},
            cells_total=int(doc.get("cells_total", 0)),
            cells_done=int(doc.get("cells_done", 0)),
            cells_failed=int(doc.get("cells_failed", 0)),
        )

    def write(self, path: Path) -> None:
        """Write atomically.

        A manifest truncated by an interrupted GPU run is worse than no manifest:
        it looks like evidence and is not.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".manifest-", suffix=".tmp")
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self.to_dict(), fh, indent=2, sort_keys=True)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    @classmethod
    def read(cls, path: Path) -> Manifest:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def run_dir(root: Path, run_id: str) -> Path:
    """Directory for *run_id* under *root*. Immutable once written (LLD §5.1)."""
    return root / run_id
