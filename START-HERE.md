# START HERE

**PROVENANCE** — verifiable and tenant-isolated LLM inference for regulated environments.

This repository contains a **complete, approved design** and a 50-task execution plan. No
application code has been written yet. Everything needed to begin implementation is here.

---

## What this project is

A public portfolio project demonstrating operational expertise with **vLLM** and **llm-d**,
framed for a regulated financial institution. Two workstreams, one repository, one thesis:
*making distributed inference auditable and information-barrier-safe.*

- **ATTEST** — batched LLM inference is not deterministic; that breaks model-risk-management
  expectations. Demonstrate the divergence, prove bitwise reproducibility under vLLM's
  batch-invariant mode, quantify what determinism costs, and emit signed, replayable
  attestation receipts.
- **BARRIER** — llm-d's prefix-cache-aware routing shares one cache namespace across tenants
  by default. Demonstrate the cross-tenant channel, then close it with a real llm-d EPP
  plugin that binds the cache salt to authenticated tenant identity.

Read `provenance-project-brief.md` for the original framing, then
`docs/design/01-requirements.md` for what was actually agreed.

---

## Read these, in this order

| # | Document | Why |
|---|---|---|
| 1 | `STATE.md` | Where the project is right now. **Always first.** |
| 2 | `docs/design/00-upstream-findings.md` | What is true upstream, verified from source. **Re-verify before writing code** — both dependencies are beta. |
| 3 | `docs/design/01-requirements.md` | 24 functional + 19 non-functional requirements, all with measurable targets. §2 holds 15 settled decisions. |
| 4 | `docs/design/02-hld.md` | Architecture, 8 components, 4 critical flows, 11 stack recommendations. |
| 5 | `docs/design/03-lld.md` | **§4 contains the frozen contracts.** Read this before writing anything. |
| 6 | `docs/design/04-execution-plan.md` | 50 tasks, 7 milestones, 15 waves, dependency graph. |
| 7 | `docs/design/06-codex-runbook.md` | How to actually run the build with Codex. |
| 8 | `docs/design/decisions.md` | Seven ADRs. Read the *conclusions*; the debates are over. |

`AGENTS.md` carries the standing rules and is loaded into every agent automatically.

---

## Three findings that shaped the design

Read these before forming your own view — each overturned an assumption in the original brief.

1. **`cache_salt` already exists in llm-d, and it is client-supplied.** The prefix hash chain
   is seeded with `TargetModel` plus an *optional* caller-provided salt. So the isolation
   primitive is already there — the gap is that it is unenforced. BARRIER must not claim to
   invent it. See `STATE.md` §F-01.
2. **Out-of-tree llm-d plugins work; no fork is needed.** `plugin.Register` and
   `plugin.Registry` are exported, as is `runner.NewRunner()`. See §F-02 and ADR-002.
3. **`cache_salt` also reaches vLLM's own engine cache**, so one derived salt can close both
   the routing index and the real KV cache — provided the plugin rewrites the outbound
   request body. See §F-03 and ADR-007.

---

## Beginning implementation

1. **Re-verify** `docs/design/00-upstream-findings.md` and update its date stamp (NFR-19).
2. **Wave 1 is `T-001` alone** — it scaffolds the tree every other task writes into. Run it
   by itself; do not parallelise it.
3. **Wave 2** is five tasks with disjoint file scopes: `T-002`, `T-003`, `T-006`, `T-008`,
   `T-009`. This is where parallelism starts paying.
4. **M0 gate** at Wave 5: `make check` green *and* `make attest-demo` green in CI — one stub
   inference travelling the full pipeline, no GPU and no cluster required.

Full mechanics — profiles, roles, the wave loop, verification routing — are in
`docs/design/06-codex-runbook.md`.

---

## What no agent can run

Nine tasks need hardware that must stay with Roshan:

- **Local kind cluster** (Docker Desktop, confirmed present): T-032, T-033, T-035, T-040,
  T-041, T-042, T-043, T-044
- **Rented NVIDIA GPU**, one staged 4–6 hour session, SM ≥ 8.0: T-028

ATTEST cannot run on the development machine at all — vLLM's batch invariance requires an
NVIDIA GPU of compute capability 8.0 or higher; AMD is untested upstream and CPU is
unsupported. Every ATTEST measurement comes from that one rented session, which is why
`T-008` builds a stub engine: it lets the entire pipeline be developed and tested with no
GPU, so integration bugs surface cheaply instead of on rented hardware.

Packs for those tasks produce **self-contained scripts that record their own output** into
`bench/results/`. Write the script; hand it over; read the result.

---

## The two risks that are still open

- **RSK-01** — divergence may not appear at Qwen2.5-0.5B. The GPU session is staged with a
  human decision point for exactly this reason. If nothing diverges, that becomes the
  published result and ATTEST's centre of gravity shifts to receipts and the APC
  non-composition finding. Requirements are written so either outcome ships.
- **RSK-02** — the llm-d simulator may expose no client-observable routing signal, since
  `x-gateway-destination-endpoint-served` is stripped from responses. `T-035` answers this,
  and the decision rule is already written down in LLD §7 — applied as written, not
  reinterpreted after seeing the result.

---

## The standard this project is held to

The README must make a senior technical reviewer at a fintech think: *this person has actually operated
this stack in an environment with auditors in it.*

That reduces to three testable properties. Every headline number traces to committed raw
output plus its command and git SHA — nothing asserted. A reviewer with no GPU and no
accounts anywhere gets a real BARRIER result within 30 minutes of cloning. And both writeups
engage with published prior art — PrefixWall (arXiv 2603.10726) and DualMap (arXiv
2602.06502) — stating plainly what is new and what is not.

Honesty is the deliverable. Overclaiming loses the exact audience this is written for.
