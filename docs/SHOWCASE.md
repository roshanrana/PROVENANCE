# PROVENANCE — Showcase

A guided tour of what the repository does, with the commands that show it. Nothing here needs a GPU, an account, or a network connection. Read [OVERVIEW.md](OVERVIEW.md) first if you want the why before the what.

## Ten minutes

```bash
uv sync
make check          # 332 Python tests and 22 Go tests, about 40 seconds
make attest-demo    # one inference through the entire ATTEST pipeline
make barrier-diff   # the mitigation, as a diff
```

What you will see:

- `make check` runs format, lint, strict type checking, the Python suite, and the Go gates in one command. CI runs the same command. If it is green here it is green there.
- `make attest-demo` (`scripts/attest_demo.py`) narrates one inference through every stage of the real architecture against a stub engine, ends with a verified signed receipt, **then tampers with the receipt and requires the verifier to exit 3**. A demo that only proves the happy path proves very little.
- `make barrier-diff` prints the three-line difference between the default and hardened deployment values. That diff is the whole argument of the BARRIER workstream.

## Feature tour

### 1. The receipt pipeline (`attest/receipt/`)

| Look at | What it shows |
|---|---|
| `attest/receipt/schema.py` | An in-toto-style statement: subject (the output), predicate (model identity, engine config, seed, sampling parameters), and the material the signature covers |
| `attest/receipt/canonical.py` | JCS canonicalisation, so two serialisations of the same receipt produce identical bytes and one signature |
| `attest/receipt/sign.py`, `cli.py` | ed25519 signing and a CLI verifier whose exit codes are a contract: 0 valid, 2 signature invalid, 3 digest mismatch, 4 malformed, 5 Hub unreachable, 6 identity divergent |
| `attest/receipt/provenance.py` | The model-identity binding: Hugging Face commit SHA and weight LFS digest |
| `tests/attest/test_receipt_cli.py`, `test_receipt_schema.py` | Receipts are mutated after signing; each mutation must fail verification with the right exit code |

**Why it is interesting:** the model identity in the receipt is the Hugging Face commit SHA plus the LFS weight digest. A validator can confirm the model that produced an output against a root the platform team does not control. The receipt is evidence rather than a claim.

### 2. The measurement harness (`attest/harness/`)

| Look at | What it shows |
|---|---|
| `matrix.py` | The experiment as data: prompts × batch shapes × seeds × invariance on/off |
| `ledger.py` | An append-only run ledger; a run that dies at cell 340 of 600 resumes at 341 |
| `engine.py`, `vllm.py` | The engine client and the process lifecycle around a real vLLM; `tests/support/stub_engine.py` is the stand-in bound by default |
| `run.py` | The driver that turns a matrix cell into raw JSONL and a receipt |

**Why it is interesting:** GPU time is the scarce resource. A resumable, ledger-backed harness means a single interrupted session is not a lost session, and the raw output is committed before any analysis reads it.

### 3. Pre-registered statistics (`common/stats/`)

| Look at | What it shows |
|---|---|
| `auc.py` | Rank-based AUC and the percentile bootstrap interval around it, in a few dozen lines |
| `permutation.py` | Permutation test for the attack-vs-mitigation comparison |
| `decision.py` | The pre-registered rule: AUC ≥ 0.75, CI excludes 0.5, *p* < 0.01 for the attack; CI contains 0.5 for the mitigation |
| `tests/common/test_stats.py` | Thirty-nine tests, including `test_bootstrap_interval_is_calibrated`: over repeated null datasets the nominal 95% interval must cover the truth about 95% of the time |

**Why it is interesting:** the decision rule was committed before any attack code existed, and the git history shows it. The implementation is deliberately readable rather than imported, so the person deciding whether a security claim holds can read the test rather than trust a call.

### 4. The tenant-salt plugin (`barrier/epp/`)

| Look at | What it shows |
|---|---|
| `barrier/epp/plugin/salt.go` | Derives a per-tenant cache salt from authenticated identity |
| `barrier/epp/plugin/plugin.go` | Registers with llm-d's exported plugin `Registry` and rewrites the outbound request so the salt reaches vLLM's own cache |
| `barrier/epp/plugin/salt_test.go` | Derivation is deterministic per tenant, distinct across tenants, and cannot be supplied by the client |
| `barrier/epp/cmd/epp/main.go` | A custom EPP binary that links the plugin without forking llm-d |
| `barrier/attack/spike_s02.py` | The timing-oracle probe, written against the pre-registered decision rule. Its verdict is that there is no client-observable oracle on the simulator: latency AUC 0.5581 [0.5026, 0.6138], p=0.0425, n=402, clearing none of the three thresholds (ADR-011, CI run #12) |
| `barrier/deploy/values-default.yaml`, `values-hardened.yaml` | The two postures; `make barrier-diff` shows the difference |

**Why it is interesting:** the finding was made by reading source. llm-d seeds its prefix hash with the model plus an optional client-supplied salt. The mitigation does not invent salting, which upstream already has; it makes the salt unforgeable and propagates it to vLLM's own cache, so both the routing index and the engine cache close together.

**And it is measured, not asserted.** GitHub Actions stands up the two-tenant kind cluster on every push, in both profiles, and runs FR-B-03 against each. In CI run #15, 40 trials per profile and n=80 per verdict: the `default` profile's probe match ratio was 1.0000 against a control of 0.0000, AUC 1.0000 [1.0000, 1.0000], p=9.999e-05, `attack_succeeds`; the `hardened` profile's probe was 0.0000, AUC 0.5000, at chance (ADR-012). The scope matters and is stated wherever the number is: **this is a confirmation oracle, not an extraction one.** The probe sends the victim's prompt verbatim, so a perfect match is true by construction. It shows an attacker who can guess a prefix having that guess confirmed; it does not show that unknown content can be recovered.

### 5. The threat model (`docs/threat-model.md`)

Read it for the precise claim: a configuration and threat-model gap in the default deployment posture, demonstrated against a cluster the project controls. Not a zero-day, not a kernel exploit, not a claim about anyone's production system.

## Query the code graph

The repo carries an offline, tree-sitter-built code knowledge graph (`graphify`, no LLM, no
network) that answers dependency and connection questions with file:line citations instead of a
grep sweep. See [`docs/graph/README.md`](graph/README.md) for the how-to and three worked
queries — among them, the shortest path from the EPP plugin's per-request hook to the
tenant-salt derivation it calls:

```
$ graphify path "RequestHeader" "DeriveSalt"
Shortest path (2 hops):
  .RequestHeader() --calls [EXTRACTED]--> .saltFor() --calls [INFERRED]--> DeriveSalt()
```

## Things worth noticing

- **Three assumptions in the original brief were overturned by reading source**, and each is recorded: `cache_salt` already exists; out-of-tree plugins work because `Register` and `Registry` are exported; the salt reaches vLLM's cache if the plugin rewrites the outbound body. Any one of these, missed, would have shipped a project that a reviewer familiar with llm-d could dismiss in thirty seconds.
- **`bench/results/` holds seven runs, including the ones that were wrong.** The two GPU stages on A40 and H100, the SGLang 2×2, the GPU cost record, S-02's run, FR-B-03's run, and a hardened run whose trust-boundary claim a later run withdrew. Each file carries its command and git SHA, and the wrong ones were corrected in place by appending rather than replaced. No measured number appears anywhere else in this repository before it appears there.
- **Negative results ship.** S-02 asked whether an ordinary caller can see a routing cache hit on the simulator and the answer was no — published as the result, with a positive control showing the EPP's prefix index matched on 402 of 404 lookups, so the negative is about observability rather than about an empty cache.
- **Design-first with gates.** Requirements, HLD, LLD with frozen contracts and a fifty-task plan preceded the first line of code. `STATE.md` is the single source of truth for where the project stands, and carries 27 findings (F-01..F-27).

## Questions this project answers, and where

| Question | Where the answer lives |
|---|---|
| How would you make an LLM's output reproducible enough for a model validator? | `attest/receipt/`, and the `VLLM_BATCH_INVARIANT` discussion in the README |
| What does determinism cost a shared platform? | `attest/analysis/cost.py` and `bench/results/`: 18.0% of throughput on SGLang, isolated from prefix caching; 22.7% on vLLM, confounded with cache loss, 95% CI [0.741, 0.808] |
| How could one tenant learn what another is asking a shared model? | `docs/threat-model.md` §3, the routing-index channel |
| Why not just tell tenants to set `cache_salt`? | README, "BARRIER", and `barrier/epp/plugin/salt.go`: a control that can be omitted is not a control |
| How do you change a platform's security posture without forking it? | `barrier/epp/cmd/epp/main.go` and `make barrier-diff` |
| How do you keep yourself honest about a security claim? | `common/stats/decision.py` and its commit date relative to the attack code |

## What it does not claim

Not a chatbot, not a RAG application, not a product. No fine-tuning, no kernel work. No claim of a vulnerability in anyone's deployment other than the one built here. No third-party SaaS anywhere in the reproduction path.
