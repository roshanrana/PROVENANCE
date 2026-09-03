# 01 — Requirements

**Project:** PROVENANCE — verifiable and tenant-isolated LLM inference for regulated environments
**Phase:** 0 (intake) · **Status:** awaiting approval · **Revision:** v0.2
**Inputs:** `provenance-project-brief.md`, `docs/design/00-upstream-findings.md`, `STATE.md` §F-01
**Date:** 2026-08-29

---

## 0. Changes since v0.1

Seven amendments, one of which changes what BARRIER actually contributes.

| # | Change | Driver |
|---|---|---|
| C-1 | **FR-B-05 rewritten.** The contribution is no longer "implement salted prefix hashing" — llm-d already has a `cache_salt`. It is now "bind the salt to authenticated tenant identity so it cannot be omitted, forged, or replayed." | F-01, read from source |
| C-2 | **FR-A-05 / FR-A-06 amended** to bind Hugging Face Hub commit SHA + LFS sha256, making model identity third-party verifiable. | Hub API verified |
| C-3 | **FR-R-07 added** — HF Space hosting the GPU-free demo and interactive writeup. Impressive tier. | Reviewer reach |
| C-4 | **FR-R-08 added** — Prometheus + Grafana in-cluster, dashboard committed. Impressive tier. | Ops signal |
| C-5 | **NFR-04 amended** — timing workloads derived from published traces rather than synthetic load. | Benchmark credibility |
| C-6 | **D-05 extended** — cite DualMap alongside PrefixWall. | Prior-art sweep |
| C-7 | **§6.4 added** — three execution environments and who runs what; new out-of-scope entry barring third-party SaaS from the reproduction path. | Environment audit, registry survey |

Resolved since v0.1: **A-03** (confirmed — index is model-scoped only), **S-03** (closed by F-01),
**S-01** (partially — source builds locally), **A-07** (Docker Desktop confirmed present).

---

## 1. Purpose

PROVENANCE is a public portfolio repository demonstrating operational expertise with vLLM
and llm-d, positioned for customer-facing implementation work in fintech and AI infrastructure. It
must read as field engineering conducted in an environment with auditors in it — not as a
tutorial.

Two workstreams, one repository, one thesis: **making distributed inference auditable and
information-barrier-safe.**

- **ATTEST** — inference reproducibility as a model-risk-management control.
- **BARRIER** — KV-cache prefix locality as a cross-tenant information leak, and its mitigation.

The primary reader is a senior technical reviewer who will skim the README for
ninety seconds, then either close the tab or read one writeup end to end. Every requirement
below is in service of that second outcome.

---

## 2. Decisions taken at intake

These are settled. Reopening any of them is a plan change requiring an entry in
`docs/design/decisions.md`.

| # | Decision | Rationale |
|---|---|---|
| D-01 | **Split BARRIER's claim.** The simulator carries the routing-index leak, the EPP plugin, and the hit-rate cost. Real vLLM carries the TTFT timing oracle. | `llm-d-inference-sim` does not vary TTFT on cache hit vs miss (issue #347, closed not-planned). Patching it ourselves would mean measuring our own assumption. |
| D-02 | **Attack the approximate prefix-cache path first**, then characterise the precise path honestly. | The approximate scorer is the default and its index is model-scoped only. Salt binding closes it cleanly; the precise path it only narrows. |
| D-03 | **One rented GPU session, 4–6 hours**, staged with an explicit go/no-go decision point. | GPU hours are the scarce resource. See §7.1. |
| D-04 | **ATTEST ships first.** | Fewer unknowns, no adversarial framing to get wrong, and the cost-of-determinism number appears to be unpublished. Builds the scaffolding BARRIER inherits. |
| D-05 | **Cite PrefixWall (arXiv 2603.10726) and DualMap (arXiv 2602.06502) prominently**, stating plainly what each covers and what remains ours. | PrefixWall covers the single-node timing channel; DualMap covers independent hash functions for routing-layer cache affinity. Both are adjacent. Ignoring either reads as unaware. |
| D-06 | **Pin prefix caching off for ATTEST's primary claim**; document the APC × batch-invariance interaction as a secondary finding. | The two features are not integrated upstream. A determinism claim with APC in an unknown state is not a claim — but the non-composition is itself a result. |
| D-07 | **Receipts are ed25519-signed with an in-toto/SLSA-style predicate**, verifiable offline. | Recognisable to both model-risk and supply-chain reviewers at no extra cost over a bespoke format. |
| D-08 | **Receipts bind the *resolved* engine configuration**, read back from vLLM — not the flags the operator intended to pass. | `override_envs_for_invariance()` mutates the environment. Intended ≠ actual. |
| D-09 | **BARRIER's statistical bar is pre-registered** before the attack is written (NFR-05). | Removes the temptation to fit the test to the result. |
| D-10 | **Private repository until ATTEST MVP lands**, then public. No fixed external deadline. | — |
| D-11 | **Primary model: Qwen2.5-0.5B-Instruct.** Escalation ladder in §7.1. | Smallest model on vLLM's tested-for-invariance list. |
| D-12 | **Model identity anchors to the Hugging Face Hub** — repo commit SHA plus LFS sha256 — not to a locally computed hash. | A self-computed hash proves internal consistency only. Anchoring to an external root is what makes the receipt an attestation rather than a log line. |
| D-13 | **No third-party SaaS in the reproduction path.** Observability is self-hosted in-cluster. | A reviewer must be able to reproduce results without creating an account anywhere. Confirmed against the connector registry: nothing there serves this project. |
| D-14 | **BARRIER's contribution is binding an existing control to identity, not inventing a control.** | F-01. `cache_salt` already exists and is client-supplied. Claiming to invent it would be caught immediately and would discredit the rest of the repo. |
| D-15 | **Three-environment execution split** (§6.4): cloud container builds and tests, Roshan's machine runs clusters, rented GPU produces ATTEST measurements. | Neither agent-reachable environment can run Kubernetes; the cloud container has Go, git and network and can compile and unit-test the plugin. |

---

## 3. Success definition

### 3.1 Project level

The project is done when the README makes a senior technical reviewer at a fintech think *this person
has actually operated this stack in an environment with auditors in it.*

Operationally, three testable properties:

- **P-01** Every headline number in the README traces to committed raw output plus the exact
  command and git SHA that produced it. Nothing is asserted.
- **P-02** A reviewer with no GPU and no accounts anywhere can run one command and see a real
  BARRIER result within 30 minutes of cloning.
- **P-03** Both writeups engage with what is already published and state plainly what is new
  and what is not.

### 3.2 Per-workstream tiers

MVP is the gate for going public; the extension is the deepening pass.

| | **MVP** | **Impressive** |
|---|---|---|
| **ATTEST** | Divergence demonstrated and quantified; bitwise reproducibility proven under invariance; cost measured with CIs; receipt generated, Hub-anchored, and independently verifiable. | Adversarial batch-composition generator that *searches* for maximally-divergent shapes; the APC × invariance non-composition finding; receipt verification as a CI gate; multi-model sensitivity curve. |
| **BARRIER** | Membership oracle against the default (unsalted) config on the simulator with pre-registered statistics; identity-bound salt plugin; oracle falls to chance when hardened; hit-rate cost table. | Real-vLLM TTFT timing oracle (D-01); salt-forgery and salt-omission attack variants; honest characterisation of the precise-path residual; p50/p99 TTFT cost; HF Space demo (FR-R-07) and Grafana dashboard (FR-R-08). |

---

## 4. Functional requirements

### 4.1 ATTEST

| ID | Requirement | Acceptance |
|---|---|---|
| FR-A-01 | Demonstrate non-determinism at temperature 0 with invariance disabled. | For a fixed prompt sampled N times under varying concurrent batch load, the harness reports unique-completion counts. A count > 1 in any load condition constitutes demonstration. If no divergence appears, that is reported as the result — see RSK-01. |
| FR-A-02 | Generate adversarial batch compositions designed to maximise divergence probability. | A committed generator produces batch schedules parameterised by concurrency, prompt-length heterogeneity, and arrival timing. Deterministic given a seed; schedules committed alongside results. |
| FR-A-03 | Prove bitwise reproducibility with invariance enabled. | Under `VLLM_BATCH_INVARIANT=1`, the same sweep yields exactly one unique completion per prompt and bitwise-identical per-token logprobs across all trials. Comparison on raw bits — not string equality, not tolerance. |
| FR-A-04 | Quantify the cost of determinism. | Throughput (output tok/s) and TTFT p50/p99, invariance on vs off, each a point estimate with a 95% confidence interval, from the same hardware in the same session. |
| FR-A-05 | Emit a signed attestation receipt per inference. | Receipt binds: output token IDs and text; **model identity as HF Hub repo id + commit SHA + `model.safetensors` LFS sha256 (D-12)**; vLLM version and git SHA; **resolved** engine configuration (D-08); attention backend; batch-invariance state; prefix-cache state; seed; full sampling parameters. |
| FR-A-06 | Verify a receipt offline, and optionally against the Hub. | `attest verify <receipt>` exits 0 for an intact receipt, non-zero with a specific diagnostic for any tampered field — no network, no engine. `attest verify --online` additionally resolves model identity against the HF Hub and reports agreement or divergence. |
| FR-A-07 | Replay a receipt against a live engine. | `attest replay <receipt>` re-runs the recorded inference and reports match/mismatch per bound field, distinguishing "output differs" from "environment differs." |
| FR-A-08 | Document the APC × batch-invariance interaction. | Secondary experiment and writeup section establishing whether the two compose and what a deployment must give up to have both. (D-06) |
| FR-A-09 | Run the entire measured sweep as one resumable script. | A single command executes the full GPU-session matrix, checkpoints after each cell, and resumes from the last checkpoint after interruption without repeating completed work. |

### 4.2 BARRIER

| ID | Requirement | Acceptance |
|---|---|---|
| FR-B-01 | Document a threat model before any attack code is written. | `docs/threat-model.md` defines tenants, trust boundaries, attacker capabilities and observations, the security property claimed, and what is explicitly not defended against. **Must state that `cache_salt` exists upstream and characterise precisely what its client-supplied nature does and does not protect.** Reviewed at the Phase 2 gate. |
| FR-B-02 | Deploy a reproducible multi-tenant llm-d topology locally. | Helm values / manifests bringing up an llm-d Router plus ≥2 simulator-backed model-server pods, ≥2 tenants, on kind. **Builds on upstream `Makefile.kind.mk` rather than hand-rolling.** No GPU. |
| FR-B-03 | Implement a membership oracle against the default configuration. | An attacker process holding only tenant-A credentials classifies whether a given prefix was recently submitted by tenant B, using only observations available to an ordinary API caller. |
| FR-B-04 | Report attack success with pre-registered statistics. | AUC with bootstrap 95% CI and a permutation-test p-value, against NFR-05. Test committed before results are collected. |
| FR-B-05 | **Bind the prefix cache salt to authenticated tenant identity**, as a real llm-d EPP plugin. | A registered Go plugin, configured through standard `schedulingProfiles` YAML, that derives the salt from the authenticated tenant identity at the gateway and **overrides any client-supplied `cache_salt`**, so the salt cannot be omitted, forged, or replayed. Cache locality is preserved within a tenant and structurally unavailable across tenants. (D-14) |
| FR-B-06 | Demonstrate all three failure modes of the stock control, and their closure. | Against the default config: (a) **omission** — attacker sends no salt and shares the honest tenant's namespace; (b) **forgery** — attacker supplies a known or guessed victim salt; (c) **negligence** — an honest tenant who never sets a salt is unprotected. Against the hardened config, all three yield AUC 95% CI containing 0.5 at equal trial count. |
| FR-B-07 | Report the cost of isolation honestly. | Prefix-cache hit rate and TTFT p50/p99, default vs hardened, on identical workload. A material cost is a finding, not a failure. |
| FR-B-08 | Characterise the precise-path residual leak. | Written analysis, and measurement where feasible, of what identity-bound routing salt does and does not close when `precise-prefix-cache-producer` is in use — where the leak lives in the engine's real cache rather than the EPP's index. Overclaiming here is the failure mode to avoid. |
| FR-B-09 | Provide the real-vLLM TTFT timing oracle as a separate result. | Impressive tier. Same statistical bar as FR-B-04, against real vLLM prefix caching. (D-01) |

### 4.3 Repository and presentation

| ID | Requirement | Acceptance |
|---|---|---|
| FR-R-01 | One command per workstream demo. | `make attest-demo` and `make barrier-demo` each produce a result from a clean clone. |
| FR-R-02 | README leads with the regulated-institution scenario. | Not a feature list. Architecture diagram, headline numbers linked to raw output, quickstart. |
| FR-R-03 | Two republishable writeups, one per workstream. | `docs/writeups/` — each standing alone, each engaging with prior art (D-05). |
| FR-R-04 | Committed raw benchmark output. | `bench/results/` holds unedited raw output plus invoking command and git SHA for every number in the README or a writeup. (P-01) |
| FR-R-05 | Architecture and threat-model documentation. | `docs/architecture.md`, `docs/threat-model.md`. |
| FR-R-06 | Reproduction instructions distinguishing GPU-free from GPU-required. | The README states plainly which results need no GPU and which do. (P-02) |
| FR-R-07 | **Hosted live demo.** | Impressive tier. A Hugging Face Space running the GPU-free BARRIER demo, plus the writeup in an interactive research-article format. CPU-only, so it fits free Spaces. Requires an HF write token (§6.4). |
| FR-R-08 | **In-cluster observability.** | Impressive tier. Prometheus + Grafana deployed into the kind cluster from committed manifests, with a dashboard showing prefix-cache hit rate and routing distribution shifting as isolation engages. Screenshot in the README. Self-hosted only (D-13). |

---

## 5. Non-functional requirements

### 5.1 Reproducibility and evidence

| ID | Requirement | Target |
|---|---|---|
| NFR-01 | Every published number is traceable. | 100% of README and writeup figures link to committed raw output + command + git SHA. |
| NFR-02 | Environments are pinned. | Locked Python dependencies, pinned Go module versions, pinned container image digests, recorded vLLM git SHA. No floating tags in the measured path. |
| NFR-03 | Harness-level determinism. | Same seed and config produce the same experiment schedule and the same analysis output. Verified by a test. |
| NFR-04 | Noise floor is measured, and workloads are realistic. | Trial counts for every timing claim derive from a measured baseline variance, with the derivation committed. **Background load replays published serving traces (e.g. BurstGPT, arXiv 2401.17644) rather than synthetic uniform load**, so latency distributions reflect real arrival patterns. |
| NFR-05 | Pre-registered statistical bar for BARRIER. | **Attack succeeds:** AUC ≥ 0.75, bootstrap 95% CI excluding 0.5, permutation p < 0.01. **Mitigation succeeds:** AUC 95% CI contains 0.5 at equal trial count. Registered in `03-lld.md` before the attack is implemented. (D-09) |

### 5.2 Performance and resource budgets

| ID | Requirement | Target |
|---|---|---|
| NFR-06 | GPU session fits the budget. | Full ATTEST measured matrix completes within **4 hours** on a single L4/A10-class GPU, with a 2-hour reserve inside the 6-hour rental. |
| NFR-07 | GPU-free demo is fast. | `make barrier-demo` completes in **≤ 15 minutes** on the Ryzen box. |
| NFR-08 | Time to first result from a clean clone. | **≤ 30 minutes** including dependencies and cluster bring-up, with no account creation anywhere. (P-02, D-13) |
| NFR-09 | Local cluster fits the hardware. | The multi-tenant topology, plus observability if enabled, runs within **48 GB RAM**. |
| NFR-10 | Receipt verification is cheap. | `attest verify` completes in **< 1 second** offline. `--online` adds one Hub API call. |

### 5.3 Engineering quality

| ID | Requirement | Target |
|---|---|---|
| NFR-11 | One command validates everything. | `make check` runs format, lint, type check, and unit tests for Python and Go, in **< 5 minutes**. Green is a precondition for any task being marked done. |
| NFR-12 | CI runs the same command. | GitHub Actions runs `make check` **and the BARRIER simulator demo** on every push. No CI-only or local-only checks. |
| NFR-13 | Coverage on logic producing published numbers. | **≥ 80%** line coverage on statistical analysis, receipt generation/verification, and the EPP plugin. Orchestration and I/O glue exempt. |
| NFR-14 | No secrets, no sensitive fixtures. | Secrets scan clean. All prompts and tenant fixtures synthetic. No real company names in MNPI-themed examples — plausible fictional ones only. |
| NFR-15 | Dependency hygiene. | Dependency audit clean at ship; findings triaged and recorded, not silently accepted. |

### 5.4 Integrity of claims

| ID | Requirement | Target |
|---|---|---|
| NFR-16 | Prior art is engaged, not ignored. | Both writeups cite adjacent published work and state what is new. (D-05, P-03) |
| NFR-17 | Negative and partial results are published. | An experiment that fails to show the expected effect appears in the repo with that conclusion. A credibility asset, not a liability. |
| NFR-18 | No vulnerability claim against llm-d. | Framing is a configuration and threat-model gap in the default deployment posture, demonstrated against our own cluster. **`cache_salt` exists and is documented as a security control; the finding is that it is unenforced, not that it is absent.** If implementation surfaces something that looks like a genuine upstream vulnerability, **stop and escalate to Roshan for responsible disclosure before anything is published.** |
| NFR-19 | Upstream facts are re-verified before implementation. | `00-upstream-findings.md` re-checked at the start of Phase 4, date stamp updated. Both dependencies are beta and moving. |

---

## 6. Constraints

### 6.1 Hardware

- **Development machine:** AMD Ryzen mini PC, 64 GB RAM, **no datacenter GPU**, Docker Desktop installed and running. Local Kubernetes via kind.
- **ATTEST cannot run on this machine.** vLLM batch invariance requires NVIDIA compute capability ≥ 8.0; AMD untested upstream, CPU unsupported.
- **Rented GPU:** one session, 4–6 hours, L4 / A10 / A100 class. The only environment producing ATTEST measurements.
- **BARRIER MVP is entirely GPU-free.** Only FR-B-09 needs the GPU, sharing the ATTEST session.

### 6.2 Upstream

- vLLM batch invariance is **beta**. Engine-wide env var, not per-request. Speculative decoding incompatible. Custom all-reduce disabled under TP. Prefix caching not integrated. DP + EP out of scope upstream.
- llm-d Router plugin interface and YAML schema are current but moving. Source is clonable and buildable (§6.4), so contracts are read from source, not inferred.
- `llm-d-inference-sim` does not model hit-vs-miss TTFT. Settled constraint (D-01).
- `cache_salt` is an optional client-supplied request field, seeded into the prefix hash chain alongside `TargetModel`. Confirmed by source (F-01).

### 6.3 Implementation

- EPP plugin in **Go**. Harnesses, benchmarks, analysis in **Python**. Deployment in **Helm / YAML**.
- Single-node, TP = 1 for ATTEST.
- Models: smallest that exhibit the phenomena honestly. Primary Qwen2.5-0.5B-Instruct (D-11).

### 6.4 Execution environments

Three environments, with a fixed division of labour. Getting this wrong wastes time, so it
is recorded rather than rediscovered. (D-15)

| Environment | Has | Does |
|---|---|---|
| **Cloud container** (agent) | Go 1.24.7, Python 3.11, uv, git, network. Docker client but **no daemon** | Source reading, Go plugin development and unit tests, Python harness and analysis development, document authoring, all `make check` work that needs no cluster |
| **Roshan's machine** | Docker Desktop, kind, the connected repo folder | All cluster bring-up, the BARRIER demo, integration runs. Agent writes scripts and manifests into the folder; Roshan executes; output lands back in the folder and the agent reads it |
| **Rented GPU** | NVIDIA SM ≥ 8.0 | ATTEST measured runs only, one staged session (§7.1) |

**Consequence for planning:** cluster-touching task packs must be self-contained scripts
that record their own output, not interactive instructions. This is checked at the Phase 3 gate.

**Credentials needed, and when.** GitHub push (Phase 4, one-time — no `gh` and no git identity
configured in either agent environment, so the first push is Roshan's). HF write token
(only if FR-R-07 proceeds). GPU provider account (Phase 6). Nothing is needed to start.

---

## 7. Assumptions and risks

**[V]** verified · **[U]** unverified, carries risk · **[R]** resolved since v0.1

| ID | Assumption | Status |
|---|---|---|
| A-01 | `VLLM_BATCH_INVARIANT=1` produces bitwise-identical output across batch shapes on supported hardware. | [V] |
| A-02 | Qwen2.5-0.5B-Instruct exhibits observable divergence with invariance off under adversarial batching. | **[U] — RSK-01** |
| A-03 | The approximate prefix index is not tenant-scoped by default. | **[R]** — confirmed: seeded with `TargetModel` + optional client `cache_salt` only |
| A-04 | Routing decisions are observable enough to a tenant-scoped caller to build a membership oracle on the simulator. | **[U] — RSK-02** |
| A-05 | A custom scorer/producer plugin can be registered without forking llm-d Router. | [U] — plugin tree located; factory signature still to read (S-01) |
| A-06 | A 4-hour matrix fits an L4/A10 at the chosen model size. | [U] — validated by the Phase 3 dry run |
| A-07 | Docker Desktop available for kind. | **[R]** — confirmed present and running |
| A-08 | The tenant identity needed to derive a salt is available to an EPP plugin at scheduling time. | **[U] — RSK-05** |
| A-09 | `cache_salt` propagates to the engine's own prefix cache, not only the EPP index. | **[U]** — determines the scope of FR-B-08; spike in Phase 2 |

### 7.1 RSK-01 — ATTEST's divergence may not appear at 0.5B *(highest project risk)*

Published demonstrations used substantially larger models with long generations. A 0.5B
model at short context may not diverge observably, collapsing FR-A-01 while leaving
FR-A-03 trivially true.

We get one GPU session to find out, so it is **staged with a decision point**:

- **Stage 1 — divergence hunt (~90 min).** Sweep an escalation ladder — Qwen2.5-0.5B →
  1.5B → 7B, short → long generations, moderate → aggressive batch heterogeneity — with
  invariance off, stopping at the first configuration showing reliable divergence.
  Cheap configurations first.
- **Decision point.** Fix model and batch schedule from measured divergence sensitivity,
  not from a guess made today.
- **Stage 2 — measured matrix (~2.5 h).** Full on/off sweep at the chosen configuration,
  at the trial counts NFR-04 requires.

**If nothing diverges in Stage 1**, that becomes the published result — a measurement of
where the effect appears and where it does not — and ATTEST's centre of gravity shifts to
the receipt and replay machinery plus the APC non-composition finding. NFR-17 exists so
this outcome ships rather than becoming a crisis.

### 7.2 RSK-02 — the simulator may not expose enough signal for the oracle

D-01 removed TTFT as usable simulator signal. The oracle must be built on what remains
observable — which pod served the request, and any header, metric, or response
characteristic revealing routing. If none of that is visible to an ordinary tenant caller,
the GPU-free MVP is at risk and falls back to FR-B-09 on real vLLM.

**Mitigation:** first thing Phase 2 establishes, before the LLD is written. A spike, not an assumption.

### 7.3 RSK-03 — upstream drift

Both dependencies are beta. An interface change between design and implementation
invalidates task packs. **Mitigation:** NFR-19, pinned versions (NFR-02), re-verification
at the start of Phase 4.

### 7.4 RSK-04 — accidental discovery of a real vulnerability

**Mitigation:** NFR-18. Stop and escalate. Nothing published.

### 7.5 RSK-05 — tenant identity may not reach the scheduling layer *(new)*

FR-B-05 assumes an EPP plugin can obtain an authenticated tenant identity at scheduling
time. If identity terminates at the proxy and is not propagated to the EPP, the salt
cannot be bound there and the mitigation must move — to the proxy, to a sidecar, or to an
`ext-proc` filter ahead of the EPP.

This does not threaten the finding, only the implementation site. **Mitigation:** resolved
by the same Phase 2 source spike as S-01; the LLD does not freeze FR-B-05's contract until
it returns. Fallback designs identified before the Phase 3 gate.

---

## 8. Out of scope

Explicitly not built, not claimed, not apologised for:

- A chatbot, a RAG application, or any end-user product.
- Fine-tuning or training of any kind.
- Novel kernel work. ATTEST *uses* vLLM's batch-invariant mode; it does not reimplement it.
- Any claim of a zero-day in llm-d, or any claim to have invented prefix-cache salting. (NFR-18, D-14)
- Multi-node deployment, disaggregated prefill/decode, or DP + EP.
- An AMD or CPU path for ATTEST — upstream does not support it.
- **Any third-party SaaS in the reproduction path** — no hosted observability, no hosted
  database, no account required to run the demos. Observability is self-hosted in-cluster. (D-13)
- Production hardening of the EPP plugin for upstream contribution. If it proves sound,
  proposing it upstream is a follow-on tracked outside this plan.
- Defending against a co-tenant with node-level or hypervisor-level access. BARRIER's
  attacker is an ordinary API caller.
- Any use of real market data, real company names in MNPI-themed fixtures, or real customer prompts.

---

## 9. Traceability

Every requirement carries an ID. The HLD maps components to requirement IDs; the LLD maps
contracts and tests to them; the execution plan maps tasks to them. A requirement with no
task, or a task with no requirement, is a defect in the plan, caught at the Phase 3 gate.

---

## 10. Open questions for the gate

Nothing blocking. Three items to note rather than decide now:

1. **RSK-01 cannot be resolved by design work.** It resolves on GPU hardware in Stage 1.
   The requirements are written so either outcome ships.
2. **A-04, A-05, A-08 and A-09 resolve by reading llm-d source and probing the topology in
   Phase 2**, not by further documentation search. They are scheduled as spikes, and the
   LLD does not freeze BARRIER's contracts until they return.
3. **FR-R-07 and FR-R-08 are impressive-tier and deliberately deferred.** They should not
   compete with ATTEST MVP for attention. Only D-12's provenance change lands early,
   because it alters a contract.
