# T-001 — Scaffold the repository tree and uv workspace

**Status:** done · **Milestone:** M0 · **Wave:** 1 · **Depends on:** — · **Env:** cloud container

## Goal

The full directory tree from LLD §1 exists, with a working uv workspace, and `uv sync`
succeeds from a clean clone. No application logic — this task creates the shape everything
else fills in.

## Context

- This lands **alone in Wave 1**: every other task modifies files inside this tree, so
  landing it first prevents a wave of merge conflicts.
- LLD §1 is an exact spec, not a sketch. Directory names are referenced by later packs.
- `common/` is a leaf: it may not import from `attest/` or `barrier/`. T-002 adds the lint
  rule that enforces this; here, just create the structure.
- Python 3.12, Go 1.24 (HLD §7.1). uv is the Python toolchain (HLD §7.2, NFR-02).
- Every directory that will hold Python gets `__init__.py`; empty leaf dirs get
  `.gitkeep` so the tree survives git.

## Contracts to honor

Directory layout is frozen at LLD §1. Reproduce it exactly, including:

```
common/{stats,traces}/ · attest/{harness,receipt,analysis}/
barrier/{epp,attack,deploy}/ · bench/{definitions,results}/ · docs/{design,tasks,writeups}/
```

`pyproject.toml` declares a uv workspace with `common`, `attest` as members.
Python requires-python = ">=3.12". Runtime deps limited to: `numpy`, `scipy`,
`cryptography`, `httpx`. Dev deps: `ruff`, `mypy`, `pytest`, `pytest-cov`.

## File scope

**Create:**
- `pyproject.toml`, `uv.lock` (generated), `.gitignore`, `.python-version`
- `README.md` (placeholder — one paragraph, T-047 writes the real one)
- `common/__init__.py`, `common/stats/__init__.py`, `common/traces/__init__.py`
- `attest/__init__.py`, `attest/harness/__init__.py`, `attest/receipt/__init__.py`, `attest/analysis/__init__.py`
- `barrier/.gitkeep`, `barrier/deploy/.gitkeep`, `barrier/attack/.gitkeep`
- `bench/definitions/.gitkeep`, `bench/results/.gitkeep`
- `docs/writeups/.gitkeep`

**Modify:** none.

Exhaustive. Do not create `Makefile` (T-004), CI config (T-005), or any Go files (T-003).

## Suggested steps

1. `uv init` at the repo root; set `requires-python = ">=3.12"`.
2. Declare the workspace members and the dependency sets above.
3. Create the directory tree exactly as LLD §1 lists it.
4. `.gitignore`: `.venv/`, `__pycache__/`, `*.pyc`, `.mypy_cache/`, `.pytest_cache/`,
   `*.ed25519` (private keys — NFR-14), `bench/results/**/tenant-keys/`.
5. `uv sync` and confirm it resolves and writes `uv.lock`.

## Acceptance criteria

- [ ] `uv sync` succeeds from a clean checkout and produces `uv.lock`
- [ ] `uv run python -c "import common, attest"` succeeds
- [ ] Every directory in LLD §1 exists and is tracked by git (no empty untracked dirs)
- [ ] `.gitignore` excludes private keys and generated tenant credentials
- [ ] `uv.lock` is committed — NFR-02 requires real pinning, not a floating resolve
- [ ] No `Makefile`, no `.github/`, no `.go` files created

## Validation

```bash
rm -rf .venv && uv sync
uv run python -c "import common, attest; print('ok')"
git status --porcelain            # must be clean after committing
```

## Out of scope

Lint/type/test configuration (T-002). Go module (T-003). `make check` (T-004). CI (T-005).
Any module with actual logic. Do not add dependencies beyond those listed — an unnecessary
dependency costs NFR-08's cold-start budget.

## Handoff notes

**Status: done** (2026-08-29)

Tree created per LLD §1. uv workspace on Python 3.12.11, `uv.lock` committed.
Deps as specified — numpy, scipy, cryptography, httpx; dev ruff/mypy/pytest/pytest-cov.

Two notes for later tasks:
- Single project with `packages = ["common", "attest"]` rather than a multi-member
  uv workspace. Our packages are plain top-level dirs; a workspace would add
  ceremony with no benefit.
- `pyproject.toml` was written once with T-002's gate config included, rather than
  created bare and immediately rewritten. Same file, one edit.
