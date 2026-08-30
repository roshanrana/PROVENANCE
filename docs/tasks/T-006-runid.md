# T-006 — `common/runid.py`: run identity and manifest construction

**Status:** done · **Milestone:** M0 · **Wave:** 2 · **Depends on:** T-001 · **Env:** cloud container

## Goal

Run identity and the run manifest exist as a small, pure, well-tested module. This is the
mechanism that makes NFR-01's traceability automatic rather than a discipline someone has
to remember.

## Context

- NFR-01 / P-01: **every published number must trace to committed raw output plus the exact
  command and git SHA.** This module is what makes that true by construction.
- LLD §5.1: `run-id` is `<workstream>-<UTC timestamp>-<git short SHA>`, so provenance is
  legible from the path alone.
- LLD §4.5 freezes the manifest schema.
- `common/` is a leaf — no imports from `attest/` or `barrier/` (enforced by T-002).
- Under strict mypy (HLD §7.3).
- A **dirty git tree must be recorded, not rejected.** Development runs happen on dirty
  trees; silently pretending otherwise is how an untraceable number gets published.

## Contracts to honor

Frozen manifest schema (LLD §4.5):

```jsonc
{ "run_id": "...", "workstream": "attest|barrier", "command": "...",
  "git_sha": "...", "git_dirty": false, "started_utc": "...", "finished_utc": "...",
  "environment": { "gpu": "...", "driver": "...", "python": "...", "vllm": "..." },
  "cells_total": 24, "cells_done": 24, "cells_failed": 0 }
```

Suggested surface:

```python
def new_run_id(workstream: Literal["attest", "barrier"], *, now: datetime | None = None) -> str
def git_state() -> tuple[str, bool]                    # (short_sha, dirty)

@dataclass(frozen=True)
class Manifest: ...
    def start(...) -> Manifest
    def finalize(self, *, cells_total, cells_done, cells_failed) -> Manifest
    def write(self, path: Path) -> None                # atomic
```

Timestamps are UTC, ISO-8601, seconds precision. `now` is injectable for testing (NFR-03).

## File scope

**Create:** `common/runid.py`, `tests/common/test_runid.py`
**Modify:** none.

Exhaustive.

## Suggested steps

1. `git_state()` via `git rev-parse --short HEAD` and `git status --porcelain`; raise a
   typed error if not a git repo rather than returning a sentinel.
2. `new_run_id()` — pure given an injected `now`.
3. `Manifest` as a frozen dataclass with `start` / `finalize` / `write`.
4. Write atomically: temp file in the same directory, then `os.replace`. A manifest
   truncated by an interrupted GPU run is worse than no manifest.
5. Tests, including the negative cases below.

## Acceptance criteria

- [ ] `new_run_id` is deterministic given a fixed `now` and git SHA
- [ ] Run-id format matches `<workstream>-<YYYYMMDDTHHMMSSZ>-<7-hex>` — asserted by regex
- [ ] `git_dirty` is `True` on a dirty tree and recorded, **not** raised as an error
- [ ] Manifest round-trips through JSON with no field loss
- [ ] `write()` is atomic — a test that interrupts between temp-write and replace leaves no
      partial file at the target path
- [ ] Typed error (not `KeyError`/`None`) when run outside a git repository
- [ ] `mypy --strict` clean; ≥80% line coverage (NFR-13)

## Validation

```bash
uv run pytest tests/common/test_runid.py -q
uv run mypy common/runid.py
uv run ruff check common/runid.py
```

## Out of scope

The ledger (T-007). Writing manifests from any real run — this module is consumed by
T-012 and later. Environment detection beyond passing a supplied dict through; GPU and
driver discovery belongs to T-018.

## Handoff notes

**Status: done** (2026-08-29)

`common/runid.py` — `new_run_id`, `git_state`, `Manifest`. 14 tests, 99% coverage,
mypy strict clean.

- Dirty trees are recorded, not rejected, as the pack required.
- `write()` is atomic via temp-file + `os.replace`, with fsync. Tested by
  monkeypatching `os.replace` to fail: no partial file, no orphaned temp.
- Added beyond the pack: `new_run_id` validates its own output against
  `RUN_ID_RE`, so a malformed SHA fails loudly instead of producing a run-id that
  no longer encodes provenance.
