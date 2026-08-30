# T-009 — `attest/receipt/schema.py`: frozen predicate types

**Status:** done · **Milestone:** M0 · **Wave:** 2 · **Depends on:** T-001 · **Env:** cloud container

## Goal

The attestation receipt schema exists as typed, validated Python objects that serialise to
exactly the frozen JSON in LLD §4.1 — and reject anything that does not.

## Context

- **This is a frozen contract (LLD §4.1).** Field names and nesting are fixed; changing one
  later is a plan change requiring sign-off and propagation to every affected task pack.
- D-12: model identity anchors to the Hugging Face Hub — repo id, commit SHA, and the
  `model.safetensors` LFS sha256 — not to a locally computed hash. A self-computed hash
  proves only internal consistency; anchoring to an external root is what makes this an
  attestation rather than a log line.
- D-08: `resolved_config` holds what the engine actually resolved, **not** the flags the
  operator intended to pass. `override_envs_for_invariance()` mutates the environment, so
  intended ≠ actual.
- Under `mypy --strict` (HLD §7.3) — this package is one of the two where a silent type
  error would corrupt a published number.
- Signing and canonicalisation are T-010. This task is types and validation only.

## Contracts to honor

in-toto Statement v1 with predicate type `https://provenance.dev/attestation/v0.1`.
Reproduce LLD §4.1 exactly. Key structures:

```python
@dataclass(frozen=True)
class ModelIdentity:
    hub: Literal["huggingface"]; repo_id: str; commit_sha: str
    weights_file: str; weights_lfs_sha256: str
    resolution: Literal["online", "offline", "unresolved"]

@dataclass(frozen=True)
class EngineState:
    vllm_version: str; vllm_git_sha: str
    resolved_config: Mapping[str, Any]
    attention_backend: str
    batch_invariant: bool; prefix_caching: bool
    speculative_decoding: bool; tensor_parallel_size: int

@dataclass(frozen=True)
class Receipt:
    model: ModelIdentity; engine: EngineState
    sampling: SamplingParams; output: OutputRecord; run: RunRef
    def to_statement(self) -> dict[str, Any]      # full in-toto Statement
    @classmethod
    def from_statement(cls, doc: Mapping[str, Any]) -> Receipt
```

`predicateType` is a module constant. Version bump rules: LLD §9 — verifiers reject unknown
majors.

## File scope

**Create:** `attest/receipt/schema.py`, `tests/attest/test_receipt_schema.py`
**Modify:** none.

Exhaustive. Do not touch `sign.py` or `cli.py` — they do not exist yet.

## Suggested steps

1. Frozen dataclasses mirroring LLD §4.1, with `Literal` types where the spec enumerates values.
2. `to_statement()` producing the full in-toto envelope, subject digest included.
3. `from_statement()` validating strictly: unknown fields rejected, missing required fields
   rejected, unknown `predicateType` major rejected.
4. A golden-file test: a committed reference receipt JSON that must round-trip byte-identically.
5. Tests for each rejection path.

## Acceptance criteria

- [ ] `to_statement()` output matches the LLD §4.1 shape field-for-field — asserted against
      a committed golden file
- [ ] `from_statement(to_statement(r)) == r` for a fully populated receipt
- [ ] **Unknown field** in the predicate is rejected with a typed error, not ignored
- [ ] **Missing required field** is rejected with a typed error naming the field
- [ ] **Unknown predicateType major version** is rejected (LLD §9)
- [ ] `resolution="unresolved"` is representable — offline operation must not require faking
      an identity (config `PROVENANCE_HF_OFFLINE`, LLD §3)
- [ ] `mypy --strict` clean on `attest/receipt/schema.py`
- [ ] ≥80% line coverage (NFR-13)

## Validation

```bash
uv run pytest tests/attest/test_receipt_schema.py -q
uv run mypy attest/receipt/schema.py       # strict mode
uv run ruff check attest/receipt/schema.py
```

## Out of scope

Signing, JCS canonicalisation, key handling (T-010). The `verify` CLI and its exit codes
(T-011). Hub resolution over the network (T-019) — this task only types the *result* of
resolution.

## Handoff notes

**Status: done** (2026-08-29)

`attest/receipt/schema.py` — frozen in-toto predicate per LLD §4.1. 18 tests,
96% coverage, mypy strict clean. Golden file at `tests/attest/golden/receipt.json`.

- Unknown fields rejected at every level, missing fields named, unknown predicate
  major rejected while a differing minor is accepted.
- **Added beyond the pack:** `SubjectDigestMismatch`, a subclass of
  `ReceiptSchemaError`. The subject digest is derived from `output.token_ids`, so
  a mismatch means the document was *edited*, not corrupted — and LLD §5 gives
  those different exit codes (3 vs 4). Without the distinct type the CLI could
  not honour that contract.
