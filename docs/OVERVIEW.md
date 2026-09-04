# PROVENANCE — Overview

**What it is:** two working controls for the shared LLM inference platforms that regulated institutions are now standing up, built against real vLLM and llm-d rather than a mock of them.

**Read this if** you want to understand what the project claims, why the claims matter to a bank, and what has and has not been demonstrated. For a guided walk through the features and the commands that exercise them, see [SHOWCASE.md](SHOWCASE.md).

---

## The setting

A large institution consolidates LLM inference onto one platform. It is the obvious move: GPUs are expensive, model governance wants one place to look, and llm-d's cache-aware routing makes the shared platform faster than any team could make its own. Equity Research, M&A Advisory, Compliance and Operations all send prompts to the same pods.

Two of the institution's oldest disciplines then collide with two of ML infrastructure's newest conveniences.

**Model risk management** (SR 11-7 in the US, and its analogues elsewhere) assumes that a model's output can be reproduced. A validator asks what the model returned on 14 March and expects a demonstrable answer. On a default vLLM deployment, the answer is that nobody can say. Batched inference is not deterministic, even at temperature 0: GPU kernels choose different reduction orders at different batch shapes, floating-point addition is not associative, and the same prompt produces different bytes depending on what else was in the batch.

**Information barriers** exist so that Research cannot see what M&A is working on. The router that makes the shared platform fast keeps a memory of which pod holds which prompt prefix, and routes matching prefixes to the warm pod. That memory is observable. A tenant who probes for a cache hit on *"Analyse the proposed acquisition of X by Y"* is probing for material non-public information, and on a default llm-d deployment two tenants on one model share one cache namespace.

PROVENANCE addresses both, as two workstreams that share a statistics library and a discipline.

## ATTEST: reproducibility as a control

ATTEST turns "we cannot reproduce it" into "here is the receipt."

vLLM ships batch-invariant kernels (`VLLM_BATCH_INVARIANT=1`) that make output independent of batch composition. The flag is engine-wide, so one caller who needs determinism imposes its cost on everyone. Nobody appears to have published what that cost is.

ATTEST does four things:

1. **Demonstrates the divergence** under adversarial batch composition, with a resumable measurement harness that drives a matrix of prompts, batch shapes and seeds through a real engine and records raw output to an append-only ledger.
2. **Proves bitwise reproducibility** once invariance is on, against the same matrix.
3. **Quantifies the cost of determinism** with bootstrap confidence intervals, so the number can go in front of a platform owner deciding whether to pay it.
4. **Emits a signed attestation receipt** for each inference: an in-toto-style statement, canonicalised with JCS, signed with ed25519, binding the output to the model identity, engine configuration, seed and sampling parameters.

The receipt's model identity is the **Hugging Face Hub commit SHA and the LFS digest of the weights**, not a locally computed hash. A validator who does not trust the platform team can confirm the identity against a root the platform team does not control. That is what separates an attestation from a log line.

## BARRIER: prefix-cache locality as a leak

BARRIER closes a channel that the default deployment leaves open.

The finding came from reading llm-d's source rather than its documentation: the prefix hash chain is seeded with the model name plus an *optional, client-supplied* `cache_salt`, and nothing else. `cache_salt` is a real, documented control. The gap is that it is unenforced: a tenant can omit it, forge another tenant's, or simply forget it. The routing index then becomes a second channel that persists in the scheduler's memory after the engine has evicted the blocks.

The mitigation binds the salt to **authenticated tenant identity** so it cannot be omitted, forged or replayed, and rewrites the outbound request so the same derived salt reaches vLLM's own prefix cache. Both channels close with one derivation.

It ships as a **registered, out-of-tree llm-d EPP scheduler plugin**. No fork. The difference between `values-default.yaml` and `values-hardened.yaml` is three lines, and that small diff is the argument: a real gap in the default posture closes with one plugin and one proxy rule.

## Why the statistics are in the repository

BARRIER's success criteria were pre-registered before any attack code existed. The bar is AUC ≥ 0.75 with a bootstrap 95% confidence interval excluding 0.5 and a permutation-test *p* < 0.01 for the attack, and a confidence interval containing 0.5 for the mitigation. The git history shows the ordering.

AUC, bootstrap and permutation are implemented in `common/stats/` rather than imported, not for lack of a library but so that a reviewer assessing whether a security claim holds can read the decision rule in forty lines. The bootstrap is calibration-tested: over two hundred null datasets, a nominal 95% interval contains the truth about 95% of the time, or the test fails.

If divergence does not appear at small model sizes, that becomes the published result, with the same rigour. The requirements are written so that either outcome ships.

## What has been demonstrated, and what needs hardware

| Claim | Status | Evidence |
|---|---|---|
| Receipt pipeline, end to end, including tamper detection | Demonstrated, no GPU | `make attest-demo` runs matrix → ledger → engine → raw JSONL → canonical receipt → signature → verification → manifest, then tampers with the receipt and requires exit code 3 |
| Statistical decision rules and their calibration | Demonstrated | `common/stats/` tests, including the 200-dataset bootstrap calibration |
| Tenant-salt derivation and plugin registration | Demonstrated | Go tests in `barrier/epp/` |
| Default-vs-hardened deployment diff | Demonstrated | `make barrier-diff` |
| Batch-composition divergence and cost of determinism | **Needs one NVIDIA GPU** (compute capability ≥ 8.0) | Batch invariance is CUDA/Triton; the harness is written and resumable |
| Two-tenant cluster topology | Needs Docker and kind, no GPU | Simulator-backed llm-d deployment |
| Timing-oracle measurement | **Needs real vLLM on a GPU** | The llm-d simulator does not vary time-to-first-token on cache hits |

No headline number appears anywhere in this repository until it traces to committed raw output plus the command and git SHA that produced it. `bench/results/` is where such numbers will live, and it is empty by design until they exist.

## Architecture in one screen

```
common/stats/     AUC, bootstrap CI, permutation test, the pre-registered rule
attest/harness/   matrix · ledger · engine client · vLLM lifecycle · run driver
attest/receipt/   in-toto schema · JCS canonicalisation · ed25519 · verify CLI
attest/analysis/  divergence tables · cost-of-determinism with CIs
barrier/epp/      Go: the tenant-salt plugin and a custom EPP binary
barrier/deploy/   kind + Helm — values-default vs values-hardened
bench/results/    immutable raw output; every published number lives here first
```

No services, no database. Eight components, all CLIs and libraries over files under git, because traceability is the requirement and a database puts published numbers behind something that can drift.

## Where it sits among the other projects

PROVENANCE is the infrastructure layer beneath the application-level projects. [REGLENS](https://github.com/roshanrana/RegLens) and [LEDGERLENS](https://github.com/roshanrana/LedgerLens) call models behind explicit contracts; PROVENANCE is about whether the platform serving those calls can be trusted by the people whose job is not to trust it. [HARBORMASTER](https://github.com/roshanrana/Harbormaster) and [SHADOWBOOK](https://github.com/roshanrana/shadowbook) share its habit of hash-chained, tamper-evident evidence.

## Further reading

- [`threat-model.md`](threat-model.md): the attacker, the assets, and the channels
- [`design/`](design/): requirements, high-level design, low-level design with frozen contracts, execution plan
- [`design/00-upstream-findings.md`](design/00-upstream-findings.md): what reading llm-d and vLLM source overturned in the original brief
- Prior art engaged with directly: [PrefixWall / CacheSolidarity](https://arxiv.org/abs/2603.10726) and [DualMap](https://arxiv.org/abs/2602.06502)
