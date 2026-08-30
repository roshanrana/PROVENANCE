# T-002 — Python quality gates: ruff, mypy, pytest

**Status:** done · **Milestone:** M0 · **Wave:** 2 · **Depends on:** T-001 · **Env:** cloud container

## Goal

ruff (lint + format), mypy, and pytest are configured and pass on the empty tree, with mypy
in **strict mode** for the two packages where a silent type error would corrupt a published
number.

## Context

- HLD §7.3: strict typing on `common/` and `attest/receipt` — these produce or validate
  published numbers. Harness glue does not need the same rigour.
- HLD §2 and LLD §2: `common/` is a leaf and must not import `attest/` or `barrier/`.
  Enforce it here with a lint rule so it can never drift.
- NFR-11 budgets **< 5 minutes** for the whole `make check`. Configuration choices here
  shape most of that.
- Coverage target is NFR-13: ≥80% lines on `common/stats`, `attest/receipt`, `barrier/epp`.
  Configure the measurement now; the threshold gate lands with T-049.

## Contracts to honor

Config lives in `pyproject.toml` (single source, no scattered dotfiles) except
`.pre-commit-config.yaml`.

Required settings:
- `[tool.ruff]` line-length 100, target py312, `select` at least `E,F,I,N,UP,B,SIM,TID`
- `[tool.ruff.lint.flake8-tidy-imports.banned-api]` — ban `attest`/`barrier` imports inside `common`
- `[tool.mypy]` default `strict = false`; per-module overrides with `strict = true` for
  `common.*` and `attest.receipt.*`
- `[tool.pytest.ini_options]` — `testpaths`, `--strict-markers`, `-q`
- `[tool.coverage.run]` — source = `common`, `attest`

## File scope

**Create:** `.pre-commit-config.yaml`
**Modify:** `pyproject.toml`

Exhaustive.

## Suggested steps

1. Add `[tool.ruff]`, `[tool.mypy]`, `[tool.pytest.ini_options]`, `[tool.coverage.run]`.
2. Add the mypy per-module strict overrides.
3. Add the banned-import rule preventing `common` from importing the workstream packages.
4. Pre-commit hooks: `ruff`, `ruff-format`, and a secrets scan (`detect-secrets` or
   `gitleaks`) — NFR-14.
5. Run all three tools on the empty tree and fix any config errors.

## Acceptance criteria

- [ ] `uv run ruff check .` and `uv run ruff format --check .` both pass
- [ ] `uv run mypy .` passes, and `mypy` reports strict mode active for `common.*` and `attest.receipt.*`
- [ ] `uv run pytest` exits 0 (collecting zero tests is fine at this stage)
- [ ] **Negative case:** a temporary file importing `attest` from inside `common/` is
      rejected by ruff. Prove it, then delete the file.
- [ ] Pre-commit config includes a secrets scan
- [ ] All three tools complete in well under the NFR-11 budget on the empty tree

## Validation

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy .
uv run pytest
# negative check
printf 'import attest\n' > common/_probe.py && ! uv run ruff check common/_probe.py; rm common/_probe.py
```

## Out of scope

Go tooling (T-003). The `make check` target itself (T-004). CI (T-005). Enforcing the
coverage *threshold* — that is T-049; here only configure measurement.

## Handoff notes

**Status: done** (2026-08-29)

ruff (E,F,I,N,UP,B,SIM,TID,RUF) + mypy + pytest + coverage, all configured in
`pyproject.toml`. mypy strict on `common.*` and `attest.receipt.*` per HLD §7.3.

- `common/` leaf rule enforced via ruff `banned-api` (TID251) with per-file-ignores
  for attest/barrier/tests/scripts. Negative case verified: a probe file importing
  `attest` from `common/` is rejected.
- **One suppression added with justification:** `ignore = ["N818"]`. N818 wants
  every exception to end in "Error"; `SignatureInvalid`, `HubUnreachable` and
  `SigningRefused` describe the condition and read better at call sites.
