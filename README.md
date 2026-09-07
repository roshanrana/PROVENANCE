# PROVENANCE

**Verifiable and tenant-isolated LLM inference for regulated environments.**

> A bank runs one shared inference platform. Equity Research and M&A Advisory both
> use it — separated by an information barrier that a compliance department spent
> real money constructing, and that an auditor will ask about.
>
> Two things break, and nobody in the ML-infra world is talking about either.
>
> A model validator asks: *"show me exactly what this model returned on 14 March,
> and prove it."* On a default vLLM deployment, the honest answer is **we cannot** —
> batched inference is not deterministic, even at temperature 0.
>
> Meanwhile, the routing layer that makes the platform fast is quietly telling
> Research what M&A has been asking about.
>
> This repository demonstrates both, and ships working fixes.

---

## Status

**Both workstreams measured and published.**

| | |
|---|---|
| Tests | **332 Python + 22 Go passing** |
| Gate | `make check` — format, lint, strict types, tests, Go build/vet/test |
| ATTEST | **Determinism costs 18.0% of throughput** on SGLang, isolated from prefix caching; 22.7% on vLLM, confounded with it. Batched inference at temperature 0 produced 34 distinct logprob vectors in 128 identical requests; vLLM's batch-invariant mode leaves 5, SGLang's leaves 1. |
| BARRIER | **The routing-index leak is real and the mitigation closes it.** Same schedule, same pre-registered rule: `default` AUC **1.0000** (p=9.999e-05, n=80), `hardened` AUC **0.5000**, at chance. ADR-012, CI run #15. |
| Figures and inferences | **[`docs/RESULTS.md`](docs/RESULTS.md)** — every result with what it does and does not support |
| Evidence | Runs in `bench/results/` **including the ones that were wrong** — two false-positive verdicts, an H100 result that was the opposite of the truth, and a claim about the trust boundary that a later run withdrew. |
| Cost | Every GPU number: about **$2.00** of rented H100/A40. Every BARRIER number: **£0**, in public CI on every push. |

Every number above traces to committed raw output plus the exact command and git
SHA that produced it. There are no placeholder numbers here, and there never
were — an unbacked figure would undermine the one thing the project is actually
claiming.

**The BARRIER result is a confirmation oracle, not an extraction one.** The probe
sends the victim's prompt verbatim, so a perfect match is by construction: it
shows that an attacker who can *guess* a prefix gets it confirmed by the routing
layer, which matters where prompts are predictable. It does not show that unknown
content can be recovered, and ADR-012 says so at the point of the claim rather
than in a footnote.

---

## At a glance

| | |
|---|---|
| **The problem** | A regulated institution's shared LLM inference platform cannot reproduce its own outputs for a model validator, and its cache-aware router leaks which prefixes other tenants have used across an information barrier. |
| **What it does** | ATTEST signed inference receipts, model identity binding to Hugging Face commits and weight digests, resumable measurement harness, pre-registered statistical decision rules, BARRIER tenant-salt threat model, llm-d EPP plugin, default-vs-hardened deployment diff. |
| **Stack** | Python 3.12, uv, pytest, ruff, mypy, NumPy/SciPy, cryptography/ed25519, Go 1.26, vLLM, **SGLang**, llm-d, Kubernetes/kind, Helm-style manifests. |
| **Validation** | `make check`, 332 Python + 22 Go tests, coverage gates, `make attest-demo`, receipt tamper tests, bootstrap/permutation/AUC tests, Go salt-derivation and salt-coverage tests compiled against real llm-d, CI mirror of local gates. The two-tenant kind topology and both deployment profiles are stood up on **every push**, and the FR-B-03 measurement runs with them. |

---

## The two workstreams

### ATTEST — reproducibility as a model-risk control

Batched LLM inference is not deterministic. The same prompt, same seed,
temperature 0, can produce different output depending on **what else happened to
be in the batch** — GPU kernels pick different reduction orders at different batch
shapes, and floating-point addition is not associative.

vLLM ships batch-invariant kernels (`VLLM_BATCH_INVARIANT=1`) that fix this. The
flag is **engine-wide, not per-request**: one caller who needs determinism imposes
the cost on everyone sharing that engine.

It also **cannot be combined with prefix caching** — the two are not integrated
upstream. That matters more than it sounds, and it is why this project measures
two engines rather than one: see below.

SR 11-7 and its international analogues assume a model's output can be reproduced
and validated. Almost nobody has connected these two facts.

**Measured, 2026-09-07, on an H100 (compute capability 9.0).** Same prompt,
temperature 0, fixed seed, concurrency 16, 128 max tokens, 128 trials per arm:

| `VLLM_BATCH_INVARIANT` | distinct logprob vectors | output throughput |
|---|---|---|
| `0` (default) | **34** of 128 | 1.00× |
| `1` | **5** of 128 | **0.773×**, 95% CI [0.741, 0.808] |

Two findings, and the second is the one that took a second run to see.

**Determinism costs about a quarter of your throughput** — 22.7%, with a
confidence interval that excludes 1.0 — plus roughly 30% on median latency. This
figure does not appear to be published anywhere.

That number is **confounded**, and saying so is the point: vLLM cannot run
batch-invariant with prefix caching on, so 22.7% is determinism *plus* the loss
of the cache. Separating them needed a second engine, and the isolated figure is
18.0% — see the SGLang decomposition below and `docs/RESULTS.md`.

**Batch invariance is a large mitigation, not a guarantee.** It cuts divergence
by ~85% at this configuration and does not eliminate it. An earlier run at 32
trials showed 6 → 1 and concluded it was fixed; that run was underpowered, and
the writeup is amended rather than deleted. Both are in `bench/results/`, along
with a third run that was simply **wrong** — and why, and how it was caught.

**The decomposition (A-03), also on the H100.** SGLang runs deterministically
*with* its radix cache on, which vLLM cannot — so the cost of determinism can be
separated from the cost of losing the cache:

| ratio | value | reading |
|---|---|---|
| D / B | **0.820×** | determinism alone costs **18.0%**, cache off both sides |
| C / D | 0.921× | the cache *costs* 7.9% on this workload rather than paying |
| C / A | 0.848× | both together — the only comparison vLLM can make |

Two results worth the trip. **The confounded number understates the cost rather
than inflating it** — the naive 0.848× against the isolated 0.820× — because in
this workload the two effects partly cancel. And **SGLang eliminated divergence
outright** (1 distinct output of 128, cache on or off) where vLLM's
batch-invariant mode left 5 of 128.

The two engines were not run under identical conditions and the writeup says so:
read them as two measurements, not a controlled comparison.

Still unmeasured: dependence on model size, batch shape and sequence length; why
vLLM's 5 residual vectors remain; confidence intervals on the 2×2; and SGLang's
Triton backend.

**What ATTEST does:** demonstrates the divergence under adversarial batch
composition, proves bitwise reproducibility once invariance is on, **quantifies
what determinism costs** — a number that does not appear to be published anywhere
— and emits a signed attestation receipt binding each output to a model identity,
engine configuration, seed and sampling parameters.

The receipt anchors model identity to the **Hugging Face Hub commit SHA and weight
LFS digest**, not a locally computed hash. A validator who does not trust us can
confirm it against a root we do not control. That is the difference between an
attestation and a log line.

**Why two engines.** On vLLM, turning determinism on means turning the prefix
cache off — so a naive "cost of determinism" number is really *determinism plus
the loss of the cache*, and nothing in the harness can separate the two. SGLang
runs deterministically **with** its radix cache on (`--enable-deterministic-inference`
on the FA3 or Triton backend). That supplies the missing cell of the
caching × determinism 2×2 and decomposes the number into its two halves. SGLang
is here as a **control arm, not as coverage**: the decomposition is the result,
not the engine count. Measured on an H100 —
`bench/results/sglang-2x2-h100-2026-09-07.md`, `docs/design/07-amendment-sglang.md`,
ADR-009.

### BARRIER — prefix-cache locality as a cross-tenant leak

llm-d's headline feature is KV-cache-aware routing: hash the prompt into blocks,
route to the pod that already holds a matching prefix, and prefill gets much
faster. Real win, real engineering.

It is also, in a multi-tenant deployment, an observable side channel — and in a
bank, **the prefixes are the sensitive part.** Probing for a cache hit on
`"Analyse the proposed acquisition of <TARGET> by <ACQUIRER>"` is probing for
material nonpublic information.

**The finding, read from source rather than documentation:** llm-d seeds its
prefix hash chain with the target model plus an *optional, client-supplied*
`cache_salt`, and nothing else. Two tenants on one model share one namespace.

**BARRIER does not claim to invent salting.** `cache_salt` is a real, documented
control. The gap is that it is **unenforced** — an attacker omits it, an attacker
forges another tenant's, or an honest tenant simply forgets. The mitigation binds
the salt to authenticated tenant identity so it cannot be omitted, forged, or
replayed, and propagates it to vLLM's own cache so both channels close.

The mitigation is a **registered llm-d EPP plugin** — out-of-tree, no fork. The
diff between `values-default.yaml` and `values-hardened.yaml` is three changes,
and that small diff is the point: a real gap closes with one plugin and one proxy
rule.

**The gap is not a vLLM quirk.** SGLang — a first-class engine in llm-d, with its
own KV-events adapter and manifests — takes the same `cache_salt` field, salts
both its radix tree and the KV events it publishes with it, and **falls back to
one shared namespace when it is absent**. Two independent engines, the same
unenforced control. One trap worth naming: SGLang's own prefix-caching docs show
`extra_key` for multi-tenancy, and `extra_key` is the *wrong* field here — it
namespaces the engine's tree but is not folded into the published event hash, so
a mitigation built on it would leave the routing-derived index shared. Read from
source at commit `30705c0`; not yet confirmed against a running engine
(`docs/design/spikes/S-03-sglang-cache-salt.md`).

---

## Quickstart

**No GPU required.** No accounts required anywhere.

```bash
uv sync
make check          # 332 Python + 22 Go tests, ~60s
make attest-demo    # the full ATTEST pipeline against a stub engine
```

`make attest-demo` takes one inference through every stage of the real
architecture — matrix cell → ledger → engine → raw JSONL → canonical receipt →
ed25519 signature → verification through the shipped CLI → manifest — then
**tampers with the receipt and requires exit code 3.** A demo that only proves the
happy path proves very little.

```bash
make barrier-diff   # the mitigation, as a diff
```

### What needs hardware

| | Needs | Why |
|---|---|---|
| ATTEST measurements | One NVIDIA GPU, compute capability ≥ 8.0 | Batch invariance is CUDA/Triton. AMD untested upstream, CPU unsupported. SGLang's deterministic mode needs FA3 or Triton to keep the radix cache. |
| BARRIER cluster demo | Docker + kind | Two-tenant llm-d topology, simulator-backed — **no GPU** |
| BARRIER timing oracle | Real vLLM on a GPU | The llm-d simulator does not vary TTFT on cache hits |

---

## Architecture

```
common/stats/     AUC, bootstrap CI, permutation test, the pre-registered rule
attest/harness/   matrix · ledger · engine client · vLLM + SGLang lifecycle · run driver
attest/receipt/   in-toto schema · JCS canonicalisation · ed25519 · verify CLI
attest/analysis/  divergence tables · cost-of-determinism with CIs
barrier/epp/      Go: the tenant-salt plugin + custom EPP binary
barrier/deploy/   kind + Helm — values-default vs values-hardened
bench/results/    immutable raw output. Every published number lives here first.
```

No services, no database. Eight components, all CLIs and libraries over files
under git — because traceability is the requirement, and a database puts published
numbers behind something that can drift.

---

## How this is built

Design-first, with gates. Requirements, HLD, LLD with frozen contracts, and a
50-task execution plan all preceded the first line of code, and each was approved
before the next began. `STATE.md` is the single source of truth for where the
project stands.

Three things worth knowing, because each overturned an assumption in the original
brief and each was found by **reading source rather than documentation**:

1. **`cache_salt` already exists**, and is client-supplied. Had this not surfaced,
   BARRIER would have shipped claiming to invent a control that upstream already
   has — and a reviewer who knows llm-d would have found that in thirty seconds.
2. **Out-of-tree llm-d plugins work.** `Register` and `Registry` are exported, so
   no fork is needed.
3. **`cache_salt` reaches vLLM's own cache too**, so one derived salt can close
   both channels — provided the plugin rewrites the outbound request body.
4. **The plugin had never compiled.** It referenced a field that does not exist in
   llm-d, and it never salted the pre-tokenized `/generate` path — so the
   "hardened" profile would have reported itself hardened while that surface
   routed in the shared namespace. Both found by building it, not by reading it,
   and both now held closed by tests that ask upstream what the hasher reads
   rather than restating a list.

### On statistics

BARRIER's success criteria were **pre-registered before any attack code existed**,
and the git history shows that ordering. The bar: AUC ≥ 0.75 with a bootstrap 95%
CI excluding 0.5 and a permutation-test p < 0.01 for the attack; a CI containing
0.5 for the mitigation.

AUC, bootstrap and permutation are implemented in this repository rather than
imported. Not for lack of a library — a reviewer assessing whether the security
claim holds should be able to read the test in forty lines rather than trust a
call. The bootstrap is calibration-tested: over 200 null datasets, a nominal 95%
interval must contain the truth about 95% of the time.

### On negative results

If divergence does not appear at small model sizes, **that becomes the published
result**, with the same rigour as a positive one. The GPU session is staged with a
human decision point for exactly this reason. Requirements are written so either
outcome ships.

---

## Prior art

This project engages with what is already published rather than around it.

**[PrefixWall / CacheSolidarity (arXiv 2603.10726)](https://arxiv.org/abs/2603.10726)**
demonstrates timing-based prompt reconstruction against shared vLLM prefix caching
and proposes selective isolation — on a single node, vanilla vLLM, with no routing
layer and no reported confidence intervals.
**[DualMap (arXiv 2602.06502)](https://arxiv.org/abs/2602.06502)** uses independent
hash functions for cache affinity in distributed serving — the performance-motivated
cousin of what BARRIER does for security.

What remains new here: the **routing-index channel**, which lives in the EPP's
memory of where it routed and therefore leaks *after* the engine has evicted the
blocks; a mitigation shipped as a working plugin rather than proposed; and
pre-registered statistics.

---

## Scope

**Not** a chatbot, a RAG application, or an end-user product. No fine-tuning. No
novel kernel work — ATTEST *uses* vLLM's batch-invariant mode. **No claim of a
zero-day in llm-d:** the framing is a configuration and threat-model gap in the
default deployment posture, demonstrated against our own cluster. No third-party
SaaS in the reproduction path.

| | |
|---|---|
| [`docs/SHIP-REPORT.md`](docs/SHIP-REPORT.md) | What is claimed, what backs it, what went wrong and what caught it |
| [`bench/results/`](bench/results/) | Every measured run — including the one that was wrong and the one that was underpowered |
| [`docs/OVERVIEW.md`](docs/OVERVIEW.md) | The setting, the two workstreams, what is demonstrated and what needs hardware |
| [`docs/SHOWCASE.md`](docs/SHOWCASE.md) | A guided tour of every component, with commands and files |
| [`docs/threat-model.md`](docs/threat-model.md) | The attacker, the assets and the channels |
| [`docs/design/`](docs/design/) | Upstream findings, requirements, HLD, LLD, execution plan, decisions |
| [`docs/design/07-amendment-sglang.md`](docs/design/07-amendment-sglang.md) | Why SGLang is here, what it costs, and what it does not buy |
| [`docs/design/spikes/`](docs/design/spikes/) | Spike records — decision rule fixed before the evidence was read |


---

## License

MIT. See `LICENSE`.
