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

**Design complete and approved. ATTEST built and tested. BARRIER in progress.**

| | |
|---|---|
| Tests | **250 passing**, 93% coverage |
| Gate | `make check` — format, lint, strict types, tests, Go gates |
| Measured results | **None yet.** No number is published until it has evidence behind it. |

Every headline number this README will eventually carry must trace to committed
raw output plus the exact command and git SHA that produced it. There are no
placeholder numbers here, and there never will be — an unbacked figure would
undermine the one thing the project is actually claiming.

## Interview Snapshot

| | |
|---|---|
| Role signal | Forward deployed AI infrastructure for regulated institutions: translate model-risk and information-barrier concerns into reproducible controls. |
| Product features | ATTEST signed inference receipts, model identity binding to Hugging Face commits and weight digests, resumable measurement harness, pre-registered statistical decision rules, BARRIER tenant-salt threat model, llm-d EPP plugin, default-vs-hardened deployment diff. |
| Implementation stack | Python 3.12, uv, pytest, ruff, mypy, NumPy/SciPy, cryptography/ed25519, Go, vLLM, llm-d, Kubernetes/kind, Helm-style manifests. |
| Validation performed | `make check`, 200+ tests, coverage gates, `make attest-demo`, receipt tamper tests, bootstrap/permutation/AUC tests, Go salt-derivation tests, CI mirror of local gates. Hardware-dependent vLLM measurements and kind cluster verification are documented as explicit next gates. |

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

SR 11-7 and its international analogues assume a model's output can be reproduced
and validated. Almost nobody has connected these two facts.

**What ATTEST does:** demonstrates the divergence under adversarial batch
composition, proves bitwise reproducibility once invariance is on, **quantifies
what determinism costs** — a number that does not appear to be published anywhere
— and emits a signed attestation receipt binding each output to a model identity,
engine configuration, seed and sampling parameters.

The receipt anchors model identity to the **Hugging Face Hub commit SHA and weight
LFS digest**, not a locally computed hash. A validator who does not trust us can
confirm it against a root we do not control. That is the difference between an
attestation and a log line.

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

---

## Quickstart

**No GPU required.** No accounts required anywhere.

```bash
uv sync
make check          # 250 tests, ~40s
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
| ATTEST measurements | One NVIDIA GPU, compute capability ≥ 8.0 | Batch invariance is CUDA/Triton. AMD untested upstream, CPU unsupported. |
| BARRIER cluster demo | Docker + kind | Two-tenant llm-d topology, simulator-backed — **no GPU** |
| BARRIER timing oracle | Real vLLM on a GPU | The llm-d simulator does not vary TTFT on cache hits |

---

## Architecture

```
common/stats/     AUC, bootstrap CI, permutation test, the pre-registered rule
attest/harness/   matrix · ledger · engine client · vLLM lifecycle · run driver
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

Threat model: `docs/threat-model.md`. Design documents: `docs/design/`.

---

## License

TBD before the repository goes public.
