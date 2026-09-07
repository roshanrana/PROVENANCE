# Low-Level Design — PROVENANCE

**Status:** draft · **HLD:** `docs/design/02-hld.md` (approved 2026-08-29)
**Requirements:** `01-requirements.md` v0.2 · **Date:** 2026-08-29

> **Contracts in §4 are frozen on approval.** Changing one afterwards is a plan change:
> update this document, list every affected task pack, get sign-off, then propagate.

---

## 0. Spike results

Three spikes gated this document. Two are resolved; one needs a cluster and is scoped below.

### S-04 — RESOLVED, and it strengthens the mitigation

`cache_salt` **is shipped in vLLM and does enter the engine's own block hash.** From vLLM's
prefix-caching design doc: the salt is "injected into the hash of the first block," and each
block hash is `hash(parent_hash, block_tokens, extra_hashes)` where extra hashes include
"cache salts to isolate caches in multi-tenant environments." Chaining carries it forward to
every downstream block.

**Consequence.** One salt can close *both* channels — the EPP's routing index and the
engine's real KV cache — provided the EPP propagates the derived salt into the outbound
request body. So FR-B-05's plugin has a third obligation the HLD did not state:

1. derive the salt from authenticated tenant identity;
2. seed the EPP prefix hash chain with it;
3. **rewrite the outbound request body's `cache_salt` to the derived value**, so the engine
   partitions its cache identically.

Without (3), the routing index is closed while the engine cache stays shared, and the
precise path keeps leaking. With it, FR-B-08's residual shrinks from "a second open channel"
to "whatever remains after both are partitioned." This is a materially better mitigation
than the HLD described, and it is now a frozen contract (§4.3).

### S-05 — RESOLVED in mechanism, deferred in placement

llm-d already implements exactly this class of defence. `pkg/epp/util/request/headers.go`
defines `InputControlHeaders` ("sent by the Gateway/User to control EPP behavior. We must
extract these, then strip them so they don't leak to the backend") and
`OutputInjectionHeaders` ("If the user sends these, they must be stripped to prevent
ambiguity"), enforced by `IsSystemOwnedHeader()` at `handlers/request.go:142` and
`handlers/response.go:202`.

The sets are hardcoded package-level vars, so our tenant header cannot join them without an
upstream change. **Placement decision: strip at the proxy** (Envoy config in
`values-*.yaml`), and have the plugin additionally fail closed if identity is absent or
malformed. Defence at the boundary, plus a plugin that refuses to guess. Recorded as
ADR-006.

### S-02 — NARROWED, still requires a cluster *(blocks §4.4 only)*

Source rules out the obvious signal: `x-gateway-destination-endpoint-served` is in
`OutputInjectionHeaders` and is **stripped from the response**, so an ordinary caller does
not learn which pod served them. `--emit-endpoint-scores` writes to Envoy dynamic metadata,
not to the client.

So the attacker-observable signal on the simulator is not yet established, exactly as RSK-02
anticipated. The spike is now precisely specified (§7) rather than open-ended, and it is the
only thing blocking §4.4. **Everything else in this document is unblocked and frozen.**

Honest early read: if the simulator exposes no client-observable routing signal, BARRIER's
GPU-free tier becomes an *operator-instrumented* demonstration — the mechanism shown from
inside the cluster via EPP metrics and routing logs, which is a legitimate and honest result
— and the attacker-observable oracle moves entirely to FR-B-09 on real vLLM. That would be a
scope change to FR-B-03, not a failure, and NFR-17 covers publishing it either way.

---

## 1. Repository layout

Phase 4 scaffolds exactly this. Treat it as a spec.

```
provenance/
├── Makefile                     # check, attest-*, barrier-*, demo targets
├── README.md                    # FR-R-02 — regulated scenario first
├── STATE.md
├── pyproject.toml               # uv workspace root
├── uv.lock                      # NFR-02
├── .github/workflows/ci.yml     # make check + make barrier-demo (NFR-12)
│
├── common/                      # shared library — the ONLY cross-workstream code
│   ├── stats/
│   │   ├── auc.py               # AUC + bootstrap CI
│   │   ├── permutation.py       # permutation test
│   │   ├── noise.py             # noise-floor estimation, trial-count derivation
│   │   └── decision.py          # pre-registered bar (NFR-05) — one implementation
│   ├── traces/replay.py         # published-trace workload replay (NFR-04)
│   └── runid.py                 # run-id + manifest construction
│
├── attest/
│   ├── harness/                 # C1 — matrix, ledger, engine driver
│   │   ├── matrix.py            # pure: (seed, config) -> cells
│   │   ├── ledger.py            # cells.jsonl state machine
│   │   ├── engine.py            # vLLM lifecycle + resolved-config readback
│   │   └── run.py               # CLI entrypoint
│   ├── receipt/                 # C2 — generate / verify / replay
│   │   ├── schema.py            # frozen predicate types (§4.1)
│   │   ├── provenance.py        # HF Hub identity resolution
│   │   ├── sign.py              # ed25519
│   │   └── cli.py               # attest verify | replay
│   └── analysis/                # C3 — tables + figures
│
├── barrier/
│   ├── epp/                     # C5 — Go module, custom EPP image
│   │   ├── go.mod               # requires llm-d-router @ pinned version
│   │   ├── cmd/epp/main.go      # blank-import plugin, run upstream runner
│   │   ├── plugin/
│   │   │   ├── plugin.go        # tenantsalt: Factory + init() registration
│   │   │   ├── salt.go          # HMAC derivation
│   │   │   └── config.go        # typed parameters
│   │   └── .ko.yaml
│   ├── attack/                  # C4 — oracle + classification  [pending S-02]
│   └── deploy/                  # C6
│       ├── values-default.yaml  # the leaking configuration
│       ├── values-hardened.yaml # the fix — this diff is the deliverable (ADR-004)
│       └── kind/                # thin wrapper over upstream Makefile.kind.mk
│
├── bench/
│   ├── definitions/             # committed experiment matrices
│   └── results/<run-id>/        # raw JSONL + manifest.json + receipts/  (immutable)
│
└── docs/
    ├── design/                  # this document and siblings
    ├── architecture.md
    ├── threat-model.md          # FR-B-01
    └── writeups/                # FR-R-03 + figures/
```

**`common/` may not import from `attest/` or `barrier/`.** Enforced by a lint rule in
`make check`. It is a leaf.

---

## 2. Conventions

| Area | Rule |
|---|---|
| Python naming | `snake_case`; modules are nouns, CLI entrypoints are `run.py` / `cli.py` |
| Go naming | Upstream idiom; plugin type string is `tenant-salt` (kebab, matching llm-d) |
| Imports | `common/` is a leaf. `attest/` and `barrier/` never import each other. |
| Errors | Python raises typed exceptions from a per-package `errors.py`; no bare `except` |
| Output | Every CLI writes structured JSONL to stdout and human text to stderr |
| Immutability | A `run-id` directory is written once. Analysis opens read-only. |
| Formatting | `ruff format`; `gofmt`. No manual formatting debates. |
| Commits | `T-###: imperative summary` — task ID mandatory (NFR-01 traceability) |
| Secrets | Never log a private key, tenant API key, EPP salt secret, or **derived salt** |

---

## 3. Configuration matrix

| Variable | Purpose | Default | Required |
|---|---|---|---|
| `PROVENANCE_RUN_ROOT` | Where `run-id` dirs are written | `bench/results` | no |
| `PROVENANCE_SIGNING_KEY` | Path to ed25519 private key | — | for signing only |
| `PROVENANCE_TEST_KEY` | Use the labelled CI fixture key | unset | no |
| `HF_TOKEN` | Hub access (public models need none) | unset | no |
| `VLLM_BATCH_INVARIANT` | Set by the harness per cell — never by hand | — | harness-managed |
| `PROVENANCE_HF_OFFLINE` | Skip Hub resolution; receipt records `identity: unresolved` | `0` | no |

Plugin config (Helm values → EPP YAML):

| Parameter | Purpose | Default |
|---|---|---|
| `identityHeader` | Header carrying proxy-vouched tenant id | `x-llmd-tenant` |
| `saltSecretRef` | K8s Secret holding the HMAC key | required |
| `propagateToEngine` | Rewrite outbound `cache_salt` (S-04) | `true` |
| `failClosed` | Reject when identity is absent/malformed | `true` |

---

## 4. Frozen contracts

### 4.1 Attestation receipt *(FR-A-05, FR-A-06)*

in-toto Statement v1 with a PROVENANCE predicate. Field names are frozen.

```jsonc
{
  "_type": "https://in-toto.io/Statement/v1",
  "subject": [{
    "name": "inference-output",
    "digest": { "sha256": "<hex of canonical output token IDs>" }
  }],
  "predicateType": "https://provenance.dev/attestation/v0.1",
  "predicate": {
    "model": {
      "hub": "huggingface",
      "repo_id": "Qwen/Qwen2.5-0.5B-Instruct",
      "commit_sha": "7ae557604adf67be50417f59c2c2f167def9a775",
      "weights": { "file": "model.safetensors", "lfs_sha256": "<hex>" },
      "resolution": "online" | "offline" | "unresolved"      // D-12
    },
    "engine": {
      "vllm_version": "0.x.y",
      "vllm_git_sha": "<hex>",
      "resolved_config": { /* read back from the engine, NOT intended flags — D-08 */ },
      "attention_backend": "<string>",
      "batch_invariant": true,
      "prefix_caching": false,                                // D-06
      "speculative_decoding": false,
      "tensor_parallel_size": 1
    },
    "sampling": { "seed": 0, "temperature": 0.0, "top_p": 1.0, "max_tokens": 256 },
    "output": { "token_ids": [ ... ], "text": "...", "logprobs_sha256": "<hex>" },
    "run": { "run_id": "...", "cell_id": "...", "timestamp_utc": "..." }
  }
}
```

Signature is detached: `receipt.json` + `receipt.sig` (ed25519 over the canonical JSON
serialisation, RFC 8785 JCS). Public key committed at `bench/results/<run-id>/receipts/pubkey.ed25519`.

**Canonicalisation is part of the contract.** Verification recomputes JCS over the parsed
document; any serialisation difference is a verification failure, not a warning.

### 4.2 `common/stats` API *(NFR-05, ADR-003)*

The repo's only cross-workstream contract. One implementation serves both the attack test
and the mitigation test — two would make the comparison meaningless.

```python
def auc(labels: NDArray[np.bool_], scores: NDArray[np.float64]) -> float: ...

def auc_bootstrap_ci(
    labels, scores, *, n_resamples: int = 10_000, confidence: float = 0.95,
    rng_seed: int,
) -> tuple[float, float, float]:            # (point, lo, hi)

def permutation_p(
    labels, scores, *, n_permutations: int = 10_000, rng_seed: int,
) -> float:                                  # two-sided

@dataclass(frozen=True)
class Verdict:
    auc: float; ci_lo: float; ci_hi: float; p_value: float
    n: int; seed: int
    attack_succeeds: bool     # auc >= 0.75 and ci_lo > 0.5 and p < 0.01
    at_chance: bool           # ci_lo <= 0.5 <= ci_hi

def decide(labels, scores, *, rng_seed: int) -> Verdict: ...

def required_trials(noise_sd: float, effect: float, *, power: float = 0.8) -> int: ...
```

Thresholds are module constants, asserted in a test against NFR-05 so the bar cannot drift
silently. Every function takes an explicit `rng_seed` — no global RNG anywhere (NFR-03).

### 4.3 Tenant-salt plugin *(FR-B-05, revised per S-04)*

Go, registered out-of-tree per ADR-002:

```go
const PluginType = "tenant-salt"

func init() {
    plugin.Register(PluginType, plugin.StabilityAlpha, Factory)
}

func Factory(name string, params *json.Decoder, h plugin.Handle) (plugin.Plugin, error)
```

Three obligations, all contractual:

| # | Obligation | Failure mode if omitted |
|---|---|---|
| 1 | `salt = HMAC-SHA256(secret, tenant_id)`, derived — never read from the client | forgery, omission |
| 2 | Seed the EPP prefix hash chain with the derived salt | routing index leaks |
| 3 | **Rewrite the outbound request body's `cache_salt` to the derived value** (S-04) | engine KV cache leaks — the precise path |

`failClosed: true` ⇒ a request with absent or malformed identity is rejected, not routed
with an empty salt. The permissive path is available for the *default* configuration only,
because that is the configuration under attack.

### 4.4 Attack oracle interface — **PENDING S-02**

Deliberately unfrozen. The classifier's score function depends on what signal the spike
finds. The contract that *is* frozen: whatever the oracle produces, it hands
`common.stats.decide()` a `labels`/`scores` pair and publishes the returned `Verdict`
verbatim. The decision rule cannot be re-litigated after seeing results.

### 4.5 Run manifest and ledger

```jsonc
// bench/results/<run-id>/manifest.json — written once, at run completion
{ "run_id": "...", "workstream": "attest|barrier", "command": "...",
  "git_sha": "...", "git_dirty": false, "started_utc": "...", "finished_utc": "...",
  "environment": { "gpu": "...", "driver": "...", "python": "...", "vllm": "..." },
  "cells_total": 24, "cells_done": 24, "cells_failed": 0 }
```

```jsonc
// cells.jsonl — append-only, one line per state transition (FR-A-09)
{ "cell_id": "...", "state": "pending|running|done|failed",
  "params": {...}, "output_path": "...", "error": null, "ts_utc": "..." }
```

Resume = replay the ledger, skip `done`, re-run `running` (assumed interrupted). `failed`
cells are **excluded from analysis, never retried into the dataset** (HLD §8.4).

---

## 5. Error taxonomy

`attest verify` — exit codes are a contract; a caller must distinguish these:

| Condition | Exit | Message | Retryable |
|---|---|---|---|
| Valid | 0 | `OK <run-id>/<cell-id>` | — |
| Bad signature | 2 | `SIGNATURE INVALID` | no |
| Field tampered | 3 | `DIGEST MISMATCH: <field>` | no |
| Malformed / unparseable | 4 | `MALFORMED: <detail>` | no |
| Hub unreachable (`--online`) | 5 | `HUB UNREACHABLE — offline verification passed` | yes |
| Hub identity divergent | 6 | `IDENTITY DIVERGENT: <field> local=<x> hub=<y>` | no |
| Test key on non-test receipt | 7 | `REFUSING: test key` | no |

Collapsing 2/3/4 into one code is a defect — a validator must be able to tell tampering
from corruption. Code 5 is the single sanctioned degradation (HLD §8.4).

Analysis refuses to emit a headline number over an incomplete matrix and names the missing
cells. Exit 8, `INCOMPLETE MATRIX: <n> cells missing`.

---

## 6. Test strategy

| Layer | Covers | Notes |
|---|---|---|
| Unit — `common/stats` | AUC/bootstrap/permutation vs scipy reference values; threshold constants vs NFR-05; determinism under fixed seed | **Hardest coverage bar (NFR-13).** A wrong statistic invalidates the project's headline claim. |
| Unit — `attest/receipt` | Round-trip sign/verify; each error-taxonomy row has a test that produces exactly that exit code; JCS canonicalisation stability; test-key refusal | |
| Unit — `attest/harness` | Matrix is a pure function of (seed, config); ledger resume semantics incl. interrupted `running` | No engine needed |
| Unit — `barrier/epp` (Go) | Salt derivation determinism; client `cache_salt` is overridden not merged; fail-closed on missing identity; outbound body rewrite | |
| Integration | Harness against a stub engine; plugin against upstream's EPP test harness | No GPU, no cluster |
| Cluster (Roshan) | `barrier-demo` end to end on kind | Self-contained script, records its own output (§6.4 of requirements) |
| GPU (one session) | ATTEST measured matrix | Staged, resumable |

External services are faked: a stub vLLM implementing only the endpoints the harness calls,
and recorded HF Hub fixtures so `verify --online` is testable offline.

---

## 7. S-02 spike — specification

Self-contained, runnable by Roshan, records its own output. This is the only thing blocking
§4.4.

**Question.** Given that `x-gateway-destination-endpoint-served` is stripped from responses,
is there *any* signal available to an ordinary tenant caller that distinguishes "my prefix
was already routed by someone else" from "it was not"?

**Method.** Stand up the default topology (2 sim pods, 2 tenants). From tenant A, with the
EPP's own metrics observed independently as ground truth:

1. **Self-collision baseline.** Send prefix P twice from tenant A. Ground truth says the
   second routes to the same pod. Test whether *any* client-visible field differs —
   response headers, body fields, `id`, timing, connection reuse.
2. **Cross-tenant probe.** Tenant B sends prefix Q; tenant A probes Q and a control prefix.
   Same observation set.
3. **Instrumented fallback.** Record EPP routing decisions and prefix-index metrics from
   inside the cluster regardless, so the *mechanism* is demonstrable even if the
   client-side channel is not.

**Outputs.** `bench/results/<run-id>/spike-s02/` with raw observations, plus a one-page
verdict: client-observable oracle viable, or not.

**Decision rule, set now.** If (1) yields no client-visible discriminator, FR-B-03 is
rescoped to the instrumented demonstration and the attacker-observable oracle moves entirely
to FR-B-09 on real vLLM. That is a scope change recorded in `decisions.md`, not a failure —
and it is published either way (NFR-17).

---

## 8. Observability plan

Logged: run manifests, ledger transitions, plugin decisions at debug (tenant id **hashed**,
never the derived salt). Never logged: private keys, tenant API keys, salt secret, derived
salts — a derived salt in a log is a forgeable credential and is in scope for the secrets
scan (NFR-14).

Metrics come from llm-d and the simulator, which already export Prometheus. FR-R-08 renders
them; nothing in the MVP depends on that rendering. No tracing — we own no distributed
request path.

---

## 9. Migration and versioning

No database, so no migrations. Two versioned surfaces: the receipt `predicateType`
(`v0.1` → bump on any field change; verifiers must reject unknown majors) and the plugin
`PluginType` config schema (additive changes only within a minor).

`bench/results/` is append-only. A re-run creates a new `run-id`; results are never
overwritten, because NFR-01 means a published number must remain resolvable forever.
