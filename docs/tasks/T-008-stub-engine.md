# T-008 — Stub vLLM engine test double

**Status:** todo · **Milestone:** M0 · **Wave:** 2 · **Depends on:** T-001 · **Env:** cloud container

## Goal

A stub HTTP server implementing only the vLLM endpoints the harness calls, with
**controllable determinism**, so the entire ATTEST pipeline can be exercised and tested in
CI with no GPU.

## Context

- ATTEST cannot run on any machine we have (requirements §6.1) — batch invariance needs
  NVIDIA SM ≥ 8.0. Without this stub, no ATTEST code could be tested until GPU day, which
  would put every integration bug on the most expensive hardware in the project.
- LLD §6: external services are faked — "a stub vLLM implementing only the endpoints the
  harness calls."
- M0's walking skeleton (T-012) runs against this stub in CI (NFR-12).
- The stub must be able to **fake divergence**: return different completions for identical
  requests when told to. That is what lets T-022's divergence analysis be tested against a
  known-correct answer instead of against hope.
- D-08: receipts bind the **resolved** engine config, so the stub must expose a
  config-readback endpoint whose contents differ from what the caller requested — otherwise
  a bug where we record intent instead of reality would pass every test.

## Contracts to honor

Endpoints (subset of the vLLM OpenAI-compatible surface):

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/completions` | Completion + `logprobs`; honours `seed`, `temperature`, `max_tokens`, `cache_salt` |
| GET | `/version` | Version string |
| GET | `/v1/models` | Model id |
| GET | `/_stub/resolved_config` | Stands in for resolved-config readback (D-08) |

Stub control (env or constructor):

```python
class StubEngine:
    divergence_mode: Literal["none", "batch_dependent", "random"]
    resolved_config_overrides: dict[str, Any]  # must differ from requested, on purpose
    latency_profile: Literal["instant", "fixed", "jittered"]
```

`divergence_mode="batch_dependent"` returns a completion that varies with concurrent
in-flight request count — mimicking the real phenomenon deterministically given a seed.

## File scope

**Create:**
- `tests/support/stub_engine.py`
- `tests/support/__init__.py`
- `tests/support/test_stub_engine.py`

**Modify:** none.

Exhaustive. The stub lives under `tests/support/`, **not** in `attest/` — it is test
infrastructure and must never be importable from production code paths.

## Suggested steps

1. Minimal ASGI app (stdlib `http.server` or a tiny ASGI app run with the existing deps —
   do **not** add a web framework dependency for this).
2. Deterministic token generation from `hash(prompt, seed, concurrency_bucket)`.
3. `divergence_mode` switch controlling whether concurrency affects output.
4. `resolved_config` endpoint returning values deliberately different from the request, so
   D-08 conformance is actually testable.
5. Context-manager fixture that starts the server on an ephemeral port and tears it down.
6. Self-tests for the stub itself — a test double that is silently wrong is worse than none.

## Acceptance criteria

- [ ] `divergence_mode="none"`: identical requests give byte-identical completions and logprobs
- [ ] `divergence_mode="batch_dependent"`: identical requests under different concurrency
      give **different** completions, reproducibly for a fixed seed
- [ ] `/_stub/resolved_config` returns at least one field differing from what was requested
- [ ] Server starts on an ephemeral port and shuts down cleanly; no port collisions when two
      instances run in the same test session
- [ ] No new runtime dependency added to `pyproject.toml`
- [ ] Stub self-tests cover both divergence modes
- [ ] `mypy` clean, `ruff` clean

## Validation

```bash
uv run pytest tests/support/test_stub_engine.py -q
uv run mypy tests/support/stub_engine.py
```

## Out of scope

The real vLLM driver (T-018). Any harness or ledger logic (T-007). Faithful latency
modelling — `latency_profile` is a stub, and no timing claim will ever be made against it
(all timing numbers come from T-028 on real hardware).

## Handoff notes

_(filled by the worker on completion)_
