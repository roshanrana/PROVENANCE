# PROVENANCE — Verifiable and Tenant-Isolated LLM Inference for Regulated Environments

**Working repo name:** `provenance`
**Status:** greenfield, design phase
**Audience for this document:** an AI coding agent that will drive design and implementation with me.

---

## 1. What this is and why it exists

I am building a public portfolio project that demonstrates deep, operational expertise with **vLLM** and **llm-d** (the CNCF-sandbox, Kubernetes-native distributed inference stack built on vLLM, Kubernetes, and the Gateway API Inference Extension). My background is enterprise financial services — backend systems, data pipelines, regulatory-driven implementation work (FINRA 4210, T+1, ISO 20022) — and the project is positioned for customer-facing implementation work at fintech and AI-infrastructure companies.

The project should read as *field engineering*, not as a tutorial. The premise is:

> When you put a distributed LLM inference stack into a regulated financial institution, two things break that nobody in the ML-infra world is talking about. Here is a reproducible demonstration of each, and here is working code that fixes them.

There are two workstreams. They ship in one repository because they tell one story: **making distributed inference auditable and information-barrier-safe.**

- **Workstream A — ATTEST:** inference reproducibility as a model-risk-management control.
- **Workstream B — BARRIER:** KV-cache prefix locality as a cross-tenant information leak, and its mitigation.

---

## 2. Problem statements

### 2.1 Workstream A — ATTEST

Batched LLM inference is not deterministic. The same prompt, same seed, same temperature 0 can produce different output depending on **what else happened to be in the batch**, because GPU kernels select different reduction orders (split-K strategies, attention split counts, normalization reductions) at different batch shapes. Floating-point addition is not associative, so a different reduction order is a different number. Published demonstrations show a single prompt sampled 1000 times at temperature 0 yielding dozens of distinct completions, identical for the first ~100 tokens and then diverging.

vLLM now ships batch-invariant kernels, enabled with `VLLM_BATCH_INVARIANT=1` (typically alongside `--compilation-config '{"cudagraph_mode": "PIECEWISE"}'`). These constrain every kernel to a single universal reduction strategy so results are bitwise identical regardless of batch size. The cost is throughput, and the flag is **engine-wide, not per-request** — one caller who needs determinism imposes the tax on every other caller sharing that engine.

Why this matters in a bank: model risk management expectations (SR 11-7 in the US, and analogous supervisory expectations elsewhere) assume a model's output can be reproduced and validated. If a model validator or a regulator asks "show me exactly what this model returned on 14 March and prove it," the honest answer on a default vLLM deployment today is *we cannot*. Almost no one has connected these two facts.

**What ATTEST builds:** a harness that (a) empirically demonstrates the divergence, (b) proves bitwise reproducibility once batch invariance is enabled, under adversarial batch composition designed to maximize the chance of divergence, (c) quantifies the throughput and latency cost precisely, and (d) emits a signed, replayable **attestation receipt** for each inference.

### 2.2 Workstream B — BARRIER

llm-d's headline performance feature is KV-cache-aware routing. The Endpoint Picker (EPP) hashes an incoming prompt into blocks, compares them against what it has previously routed to each pod, and sends the request to the pod that already holds the matching prefix so vLLM's prefix caching actually fires. This is a large, real win on time-to-first-token.

It is also, in a multi-tenant deployment, an observable side channel. A prefix cache hit is dramatically faster than a cold prefill. If TTFT is observable to a caller — and it always is — then a caller can **probe whether a given prefix has been processed recently by someone else**.

In a financial institution the prefixes are the sensitive part. Probing for a cache hit on `"Analyze the proposed acquisition of <TARGET> by <ACQUIRER>"` is probing for material nonpublic information. Probing shared desk-level system prompts crosses an information barrier that a compliance department spent real money constructing. The performance feature and the control are in direct conflict, and the default configuration silently picks performance.

**What BARRIER builds:** a reproducible timing oracle against a shared llm-d deployment showing statistically significant prefix-membership inference, followed by a **mitigation implemented as an actual EPP plugin** — tenant-scoped/salted prefix hashing so that cache locality is preserved *within* a tenant and structurally unavailable *across* tenants — plus honest measurement of the hit-rate and TTFT cost of that isolation.

---

## 3. Scope and deliverables

### Repository deliverables

1. **`attest/`** — reproducibility harness, adversarial batch-composition test generator, benchmark suite, receipt generation and verification CLI.
2. **`barrier/`** — attack harness (timing oracle + statistical analysis), the EPP plugin implementing tenant-scoped prefix isolation, and configuration to deploy it.
3. **`deploy/`** — Helm values / manifests for a reproducible llm-d deployment on a local cluster, including a multi-tenant scenario with at least two tenants and a shared pod pool.
4. **`bench/`** — reproducible benchmark definitions and a results directory with committed raw output, so numbers in the README are auditable rather than asserted.
5. **`docs/`** — architecture, threat model, and two writeups (one per workstream) suitable for republication as blog posts.
6. **`README.md`** — leads with the regulated-institution scenario, not a feature list. Architecture diagram. Headline numbers. Quickstart.

### Non-goals

- Not building a chatbot, a RAG application, or any end-user product.
- Not fine-tuning or training anything.
- Not attempting novel kernel work; ATTEST *uses* vLLM's batch-invariant mode, it does not reimplement it.
- Not claiming a zero-day in llm-d. The framing is a **configuration and threat-model gap in the default deployment posture**, demonstrated against my own cluster. If implementation work surfaces something that looks like a genuine upstream vulnerability, stop and flag it to me for responsible disclosure before anything is published.

---

## 4. Environment and constraints

- **My hardware:** AMD Ryzen mini PC, 64GB RAM, no datacenter GPU. Local Kubernetes via kind or k3s.
- **GPU access:** Workstream A requires at least one real CUDA GPU, since batch-invariant kernels are Triton/CUDA. Assume I will rent a single mid-range GPU (L4/A10/A100 class) by the hour for benchmark runs. **Design ATTEST so that development and iteration happen locally and only the measured benchmark runs need the rented GPU** — GPU hours are the scarce resource, so batch every experiment into as few sessions as possible and make runs resumable and fully scripted.
- **GPU-free path:** llm-d publishes `llm-d-inference-sim`, a lightweight simulator that mimics vLLM's behavior without GPUs. Workstream B's routing, scheduling, and plugin work should be developed and demonstrated against the simulator so the whole attack-and-mitigation story is reproducible by a reviewer with no GPU at all. Validate against real vLLM where it matters, but do not make a GPU a prerequisite for running the demo.
- **Languages:** EPP plugins are Go. Harnesses, benchmarks, and analysis in Python. Deployment in Helm/YAML.
- **Models:** use the smallest models that still exhibit the phenomena honestly (small Qwen or Llama variants). Model size is not the point of either workstream.

### Verify before you build

This ecosystem is moving fast and my knowledge of it is not current. Before committing to any API surface, **check the live upstream docs and source**, specifically:

- Current vLLM batch-invariance flags, supported backends, and documented limitations.
- The current llm-d plugin interface. Note the Inference Scheduler has been renamed to the llm-d Router, and the EPP has both a Scheduling layer (filters/scorers) and an optional Flow Control layer. Confirm the current plugin registration mechanism, YAML config schema, and which prefix-cache scorers ship by default (there are at least a prefix-cache scorer and a more precise variant that reads actual engine cache state — the distinction matters a lot for the threat model, since one tracks the EPP's own routing history and the other reflects real KV-cache contents).
- Whether the simulator models prefix-cache hit latency faithfully enough to carry the timing-oracle demo, or whether that part needs real vLLM.

---

## 5. What "done" looks like

**ATTEST is done when** a reviewer can run one command and see: a table of unique-completion counts for a fixed prompt under varying concurrent batch load with invariance off; the same table with invariance on showing exactly one unique completion and bitwise-identical logprobs; a clear throughput/TTFT delta quantifying the cost of determinism; and a receipt that can be independently verified to bind a specific output to a specific model hash, engine version, kernel configuration, seed, and sampling parameters.

**BARRIER is done when** a reviewer can run one command and see: an attacker process correctly classifying whether a target prefix was recently queried by a different tenant, at an accuracy meaningfully above chance, with the statistical test shown rather than asserted; then the same attack run against the hardened configuration falling to chance; alongside an honest table of what the isolation cost in cache hit rate and p50/p99 TTFT.

**The project is done when** the README makes a senior technical reviewer at a fintech think *this person has actually operated this stack in an environment with auditors in it.*

---

## 6. How I want to work with you

Start with design, not code. Specifically, I want first:

1. A **threat model** for BARRIER — who the tenants are, what the attacker controls, what they observe, and what "isolation" formally means here. Get this right before writing the attack.
2. A **measurement design** for both workstreams. The single biggest failure mode for this project is unconvincing benchmarks. Decide up front how many trials, what the noise floor is, how to control for unrelated load, and what statistical test makes the BARRIER claim defensible.
3. A **repository and phasing plan** with a defined minimum viable version and a defined "impressive" version for each workstream, so I can ship something real early and deepen it.

Then flag the open design questions you want me to decide before implementation begins, rather than assuming defaults. I would rather answer five sharp questions now than refactor later.

Ask me about anything above that is ambiguous or that your reading of the current upstream docs contradicts. If something in this brief is factually stale, say so directly — I wrote it from a snapshot and the ecosystem has probably moved.
