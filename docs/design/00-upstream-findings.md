# 00 — Upstream Verification Findings

**Date of verification:** 2026-08-28
**Purpose:** The project brief was written from a snapshot. Before any design work, verify
the API surfaces both workstreams depend on. This document records what is true upstream
today, what in the brief is stale, and what constraints those facts impose on the design.

Every claim here is sourced. Re-verify before Phase 4 (implementation) — this ecosystem
moves fast enough that a two-month-old fact is a liability.

---

## 1. vLLM batch invariance (ATTEST dependency)

### 1.1 What is confirmed

| Item | Status |
|---|---|
| Enable mechanism | `VLLM_BATCH_INVARIANT=1` environment variable. Confirmed. |
| Scope | Engine-wide (process env var), **not per-request**. The brief's central claim holds. |
| Hardware | NVIDIA GPUs, **compute capability ≥ 8.0**. |
| Maturity | Documented as beta / under active development. |
| Mechanism | Torch-level op overrides: `matmul`, `bmm`, `addmm`, `linear`, `softmax`, `log_softmax`, `mean`, `rms_norm`, plus a fixed attention block size (`AttentionBlockSize`, `get_batch_invariant_attention_block_size()`). |
| Env overriding | The module exposes `override_envs_for_invariance()` — vLLM now sets required backend/compile env itself. |
| Tested models | DeepSeek V3/R1/V3.1, Qwen3 (dense + MoE), Qwen2.5 (0.5B–32B), Llama 3.1/3.2, GPT-OSS 20B/120B, Mistral 7B v0.3. |

Compute capability 8.0+ covers the rental targets in the brief: A100 (8.0), A10 (8.6),
L4 (8.9). All viable. **AMD is explicitly untested and CPU is unsupported** — so the
Ryzen mini PC cannot run ATTEST's measured path at all, only its analysis and tooling.

### 1.2 What is stale in the brief

- **`--compilation-config '{"cudagraph_mode": "PIECEWISE"}'` is no longer something the
  operator must pass.** `override_envs_for_invariance()` handles the compile/backend
  environment internally. Passing it by hand is at best redundant and at worst wrong.
  **Design impact:** ATTEST must record the *resolved* engine configuration in the
  receipt, not the flags the operator intended to set. Reading back what vLLM actually
  resolved is the only honest attestation.

### 1.3 Constraints the design must absorb

These are the findings that change what we can claim, in descending order of impact.

1. **Prefix caching is not yet integrated with batch invariance.** This is the single
   most consequential finding for ATTEST. A determinism claim made with APC in an
   unknown state is not a claim at all. ATTEST must pin prefix-cache state explicitly,
   record it in the receipt, and treat "reproducible" as scoped to that state.
   It also creates a genuine engineering finding worth writing up: *the two features a
   regulated deployment most wants — determinism and cache efficiency — do not currently
   compose.* That is a better story than the brief anticipated.
2. **Speculative decoding is incompatible.** Must be off, and must be asserted in the receipt.
3. **Custom all-reduce is disabled under tensor parallelism.** Part of the cost we are
   measuring; note it rather than treat TP overhead as a mystery.
4. **DP + EP is out of scope upstream.** Keep the ATTEST rig single-node, TP=1. The brief
   already leans this way; this makes it a hard constraint rather than a preference.

### 1.4 Performance context

vLLM's own tracking issue reports optimization deltas (≈18% throughput, ≈10.7% TTFT,
≈28.9% E2E latency improvements) — but those are **improvements to the batch-invariant
path over its earlier self**, not the cost of invariance versus default. The number the
brief wants — the price of determinism — is not published anywhere we found.

**This is ATTEST's most valuable single output.** Measuring it credibly is the deliverable,
which raises the bar on the benchmark design accordingly.

---

## 2. llm-d (BARRIER dependency)

### 2.1 Naming and repo layout

The brief is correct: the **Inference Scheduler has been renamed the llm-d Router**
(`llm-d/llm-d-router`). APIs previously in the Gateway API Inference Extension (GIE)
repo have been consolidated into it. `llm-d-inference-scheduler` is the historical name.

Architecture is a **Proxy** (Envoy / Istio / Envoy AI Gateway) plus an **Endpoint Picker
(EPP)** consulted per request over `ext-proc`.

### 2.2 Plugin framework — confirmed shape

Plugin types: **Filter**, **Scorer**, **Picker**, **PreRequest**, **PostResponse**,
**DataProducer**, **ProfileHandler**.

Config schema:

```yaml
- name: instance-name      # optional, defaults to type
  type: plugin-type
  parameters:
    key: value

schedulingProfiles:
  - name: profile-name
    plugins:
      - pluginRef: plugin-instance
        weight: 50          # scorers only
```

Flow Control is **off by default**, gated behind `featureGates: ["flowControl"]`, with
defaults `fcfs-ordering-policy`, `global-strict-fairness-policy`,
`static-usage-limit-policy`, `utilization-detector`.

**Open:** the exact Go registration call and factory signature is not in the docs we can
reach; it needs to be read from source (`pkg/epp/framework/plugins`, `cmd/`) during LLD.
Flagged as a Phase 2 investigation task rather than guessed at now.

### 2.3 The distinction that carries the whole threat model

The brief suspected this mattered. It matters more than it guessed.

| | Approximate | Precise |
|---|---|---|
| Plugins | `approx-prefix-cache-producer` (DataProducer) + `prefix-cache-scorer` (Scorer) | `token-producer` + `precise-prefix-cache-producer` + `prefix-cache-scorer` + KV-Cache Indexer |
| Tokenization | character-to-token ratio estimate, no tokenizer | exact, via vLLM's HTTP render endpoint |
| State source | **in-EPP LRU index of the EPP's own routing history** | **real engine KV-cache contents**, streamed over ZeroMQ |
| Config | default | `prefixMatchInfoProducerName: precise-prefix-cache-producer` |

Both hash the prompt into rolling-hash chains over fixed blocks (~16 tokens).

**These are two different vulnerabilities, not one:**

- **Approximate** leaks the EPP's *routing memory*. It is observable even when the engine
  has evicted the KV blocks entirely. An attacker learns "someone routed this prefix
  recently," which is a membership oracle on prompt content and survives cache pressure.
  It is also a **single global index shared across all tenants** — the structural gap.
- **Precise** leaks *real cache residency*, which is the classic timing channel, but is
  bounded by actual eviction and therefore has a shorter memory.

The mitigation must therefore be evaluated against **both**, and the writeup should treat
them as separate results. A tenant-salted hash fixes the approximate path cleanly (it is
EPP-local state we control). The precise path is harder — the leak is in the engine's real
cache, so salting the EPP index alone does not close it. **Expect the honest conclusion to
be that routing-layer salting closes one channel fully and narrows the other**, and say so
rather than overclaiming.

### 2.4 Simulator fidelity — a blocking constraint

**`llm-d-inference-sim` does not reduce simulated TTFT on prefix-cache hits.** Issue #347
("Block-Level KV Cache Tracking for Prefix-Aware Scorer Validation"), which proposed
exactly that (`--kv-cache-blocks`, `--kv-block-size`, `--prefix-cache-enabled`), was
**closed as not planned**. The simulator exposes only a synthetic `gpu_cache_usage_perc`
float that drifts; it does publish ZMQ block allocation/eviction events and models TTFT
with load-dependent scaling and configurable jitter, but hit-vs-miss is not in the
latency model.

**Consequence for the brief's GPU-free promise:** the timing-oracle half of BARRIER
cannot run on the stock simulator. A cache hit and a cache miss are the same speed there.
Building the oracle against a simulator we patched ourselves to produce the timing gap
would be circular — we would be measuring our own assumption.

The split that survives this honestly:

- **Simulator can carry:** routing behavior, the cross-tenant index-sharing demonstration,
  the EPP plugin itself, hit-rate cost of isolation, and the full deploy story.
  This is real: routing decisions are observable and the leak is in the EPP's index,
  which the simulator does model.
- **Simulator cannot carry:** the TTFT timing oracle. That needs real vLLM prefix caching.

See open question Q2 — this is a decision for Roshan, not a default to assume.

---

## 3. Prior art — a framing correction

The brief states that almost no one has connected these facts. For **ATTEST** that
appears to hold: we found no published measurement of determinism's cost framed as a
model-risk control.

For **BARRIER** it does not. **PrefixWall / CacheSolidarity (arXiv 2603.10726)** already
demonstrates timing-based prompt reconstruction against shared vLLM automatic prefix
caching and proposes selective prefix isolation, evaluated on nine models (0.5B–13B) on a
single A100, reporting up to 70% higher cache reuse and 30% lower latency than blanket
user isolation.

This does not sink BARRIER, but the framing must change or the project loses credibility
with precisely the readers it is trying to impress. What remains genuinely ours:

1. **The routing layer.** PrefixWall is explicitly single-node vanilla vLLM. It does not
   touch distributed routing, disaggregated prefill/decode, or an EPP-held index. The
   approximate scorer's cross-tenant routing-history index is a channel that paper does
   not describe.
2. **A shipped mitigation in a real system.** They propose a mechanism; we ship a
   registered llm-d plugin with deployable config.
3. **Statistical rigor.** The paper reports no confidence intervals or p-values. The brief
   already identified unconvincing benchmarks as this project's biggest failure mode —
   doing the statistics properly is a differentiator, not overhead.
4. **The regulated-institution frame.** Information barriers and MNPI, not generic
   "prompt stealing."

**Recommendation:** cite PrefixWall prominently in the BARRIER writeup and position
against it explicitly. A portfolio project that engages with adjacent literature reads as
senior work; one that ignores it reads as unaware.

---

## Sources

- [vLLM — Batch Invariance](https://docs.vllm.ai/en/latest/features/batch_invariance/)
- [vLLM — `batch_invariant` module API](https://docs.vllm.ai/en/latest/api/vllm/model_executor/layers/batch_invariant/)
- [vLLM issue #27433 — Batch Invariant Feature and Performance Optimization](https://github.com/vllm-project/vllm/issues/27433)
- [vLLM issue #40628 — RFC: Batch Invariance Dispatching in vLLM IR](https://github.com/vllm-project/vllm/issues/40628)
- [llm-d Router — architecture](https://llm-d.ai/docs/dev/architecture/core/router)
- [llm-d/llm-d-router](https://github.com/llm-d/llm-d-router)
- [llm-d — Prefix-Cache Aware Routing](https://llm-d.ai/docs/architecture/advanced/kv-management/prefix-cache-aware-routing)
- [llm-d — Precise Prefix Cache Aware Routing](https://llm-d.ai/docs/guide/Installation/precise-prefix-cache-aware)
- [llm-d/llm-d-inference-sim](https://github.com/llm-d/llm-d-inference-sim)
- [llm-d-inference-sim issue #347 — Block-Level KV Cache Tracking](https://github.com/llm-d/llm-d-inference-sim/issues/347)
- [PrefixWall / CacheSolidarity — arXiv 2603.10726](https://arxiv.org/html/2603.10726v2)
