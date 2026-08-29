"""The cell ledger — append-only run state that survives interruption.

FR-A-09. This is deliberately dumber than a workflow engine, because what it has
to survive is a dropped SSH session to rented hardware halfway through a paid GPU
session. An append-only JSONL file, replayed on startup, does that; anything with
its own state machine and daemon does not.

Resume semantics (LLD §4.5): replay the ledger, skip ``done``, re-run ``running``
(assumed interrupted). ``failed`` cells are **excluded from analysis and never
retried into the dataset** — a cell that errored and silently re-succeeded would
put a survivor-biased number in a published table (HLD §8.4).
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from common.runid import iso, utc_now


class CellState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass(frozen=True)
class CellRecord:
    cell_id: str
    state: CellState
    params: Mapping[str, Any]
    output_path: str | None = None
    error: str | None = None
    ts_utc: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "state": self.state.value,
            "params": dict(self.params),
            "output_path": self.output_path,
            "error": self.error,
            "ts_utc": self.ts_utc,
        }

    @classmethod
    def from_dict(cls, doc: Mapping[str, Any]) -> CellRecord:
        missing = {"cell_id", "state", "params"} - set(doc)
        if missing:
            raise ValueError(f"ledger record missing field(s): {sorted(missing)}")
        return cls(
            cell_id=doc["cell_id"],
            state=CellState(doc["state"]),
            params=dict(doc["params"]),
            output_path=doc.get("output_path"),
            error=doc.get("error"),
            ts_utc=doc.get("ts_utc", ""),
        )


class Ledger:
    """Append-only ledger over ``cells.jsonl``.

    Every transition is a new line. The current state of a cell is the last line
    mentioning it — so the file is a log, never a mutable record, and a partial
    write can lose at most the final transition.
    """

    FILENAME = "cells.jsonl"

    def __init__(self, path: Path, *, now: Any = None) -> None:
        self.path = path
        self._now = now or utc_now

    @classmethod
    def in_dir(cls, directory: Path, *, now: Any = None) -> Ledger:
        return cls(directory / cls.FILENAME, now=now)

    # ---------------------------------------------------------------- writing

    def _append(self, record: CellRecord) -> CellRecord:
        stamped = CellRecord(
            cell_id=record.cell_id,
            state=record.state,
            params=record.params,
            output_path=record.output_path,
            error=record.error,
            ts_utc=record.ts_utc or iso(self._now()),
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(stamped.to_dict(), sort_keys=True) + "\n"
        # Append + fsync: an interrupted run must not lose a transition it
        # already reported, or resume will redo paid GPU work.
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
        return stamped

    def seed(self, cells: Iterable[Mapping[str, Any]]) -> list[CellRecord]:
        """Write the initial ``pending`` records. Idempotent: seeding twice is a no-op."""
        if self.path.exists() and self.records():
            return list(self.states().values())
        return [
            self._append(CellRecord(c["cell_id"], CellState.PENDING, c.get("params", {})))
            for c in cells
        ]

    def mark_running(self, cell_id: str) -> CellRecord:
        return self._append(CellRecord(cell_id, CellState.RUNNING, self._params(cell_id)))

    def mark_done(self, cell_id: str, output_path: str) -> CellRecord:
        return self._append(
            CellRecord(cell_id, CellState.DONE, self._params(cell_id), output_path=output_path)
        )

    def mark_failed(self, cell_id: str, error: str) -> CellRecord:
        return self._append(
            CellRecord(cell_id, CellState.FAILED, self._params(cell_id), error=error)
        )

    # ---------------------------------------------------------------- reading

    def records(self) -> list[CellRecord]:
        """All transitions, in order. A truncated final line is dropped, not fatal.

        A power cut mid-write should cost the last transition, not the whole run.
        """
        if not self.path.exists():
            return []
        out: list[CellRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                out.append(CellRecord.from_dict(json.loads(line)))
            except (json.JSONDecodeError, ValueError):
                continue
        return out

    def states(self) -> dict[str, CellRecord]:
        """Current state per cell — the last transition wins."""
        latest: dict[str, CellRecord] = {}
        for record in self.records():
            latest[record.cell_id] = record
        return latest

    def _params(self, cell_id: str) -> Mapping[str, Any]:
        record = self.states().get(cell_id)
        return record.params if record else {}

    def resumable(self) -> Iterator[CellRecord]:
        """Cells still to run: ``pending`` and ``running`` (the latter interrupted).

        ``failed`` is *not* resumable. That is the whole point of the state.
        """
        for record in self.states().values():
            if record.state in (CellState.PENDING, CellState.RUNNING):
                yield record

    def counts(self) -> dict[str, int]:
        tally = {s.value: 0 for s in CellState}
        for record in self.states().values():
            tally[record.state.value] += 1
        return tally

    def is_complete(self) -> bool:
        return not any(self.resumable())


def now_iso() -> str:
    return iso(datetime.now(UTC))
