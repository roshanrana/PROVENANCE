# START HERE

**PROVENANCE** — verifiable and tenant-isolated LLM inference for regulated environments.

This repository is **shipped**. Both workstreams have their headline result measured,
`make check` is green at **318 Python and 22 Go tests**, and no number is published here
that does not trace to raw output committed under `bench/results/`.

Four places to start, in this order: `README.md` for the claims, `docs/SHIP-REPORT.md` for
what is established and what is not, `bench/results/` for the seven runs behind both
workstreams — including the ones that were wrong — and `docs/design/decisions.md` for the
twelve ADRs that got there.

---

## What this project is

Operational work against **vLLM**, **SGLang** and **llm-d**, framed for a regulated
financial institution. Two workstreams, one repository, one thesis: *making distributed
inference auditable and information-barrier-safe.*

- **ATTEST** — batched LLM inference is not deterministic; that breaks model-risk-management
  expectations. Measured on rented H100/A40 for about **$2.00** total: at temperature 0,
  128 identical requests produced **34 distinct logprob vectors**. vLLM's batch-invariant
  mode leaves 5 of 128; SGLang's deterministic mode leaves 1. Determinism costs **18.0%**
  of throughput on SGLang, isolated from prefix caching (D/B ratio 0.820), and **22.7%** on
  vLLM, where it is confounded with cache loss (95% CI [0.741, 0.808]). Each inference can
  carry a signed, replayable attestation receipt.
- **BARRIER** — llm-d's prefix-cache-aware routing shares one cache namespace across tenants
  by default. The channel is demonstrated and closed by a real, out-of-tree llm-d EPP plugin
  that binds the cache salt to authenticated tenant identity. Measured in CI run #15
  (ADR-012), 40 trials per profile, n=80 per verdict: the `default` profile's probe match
  ratio is **1.0000** against a control of 0.0000, AUC **1.0000** [1.0000, 1.0000],
  p=9.999e-05, `attack_succeeds`; the `hardened` profile's probe is 0.0000 against the same
  control, AUC **0.5000**, at chance.

**The BARRIER result is a confirmation oracle, not an extraction one.** The probe sends the
victim's prompt verbatim, so a perfect match is true by construction. It shows that an
attacker who can *guess* a prefix gets that guess confirmed by the routing layer. It does
not show that unknown content can be recovered, and ADR-012 says so at the point of the
claim.

Read `provenance-project-brief.md` for the original framing, then
`docs/design/01-requirements.md` for what was actually agreed.

---

## Read these, in this order

| # | Document | Why |
|---|---|---|
| 1 | `STATE.md` | Where the project is right now, and 27 recorded findings (F-01..F-27). **Always first.** |
| 2 | `docs/SHIP-REPORT.md` | What is claimed, what backs it, what went wrong, and what is not done. |
| 3 | `bench/results/` | Seven result files, immutable, including the runs that were wrong and the reason attached to each. |
| 4 | `docs/design/00-upstream-findings.md` | What is true upstream, verified from source. Both dependencies are beta; re-verify before changing code against them. |
| 5 | `docs/design/01-requirements.md` | 24 functional + 19 non-functional requirements, all with measurable targets. §2 holds 15 settled decisions. |
| 6 | `docs/design/02-hld.md` | Architecture, 8 components, 4 critical flows, 11 stack recommendations. |
| 7 | `docs/design/03-lld.md` | **§4 contains the frozen contracts.** |
| 8 | `docs/design/04-execution-plan.md` | 50 tasks, 7 milestones, 15 waves, dependency graph. |
| 9 | `docs/design/decisions.md` | Twelve ADRs (ADR-001..ADR-012). Read the *conclusions*; the debates are over. |

`handoff/claude-code/RUNBOOK.md` and `handoff/codex/RUNBOOK.md` describe how the build was
actually driven — profiles, roles, the wave loop, verification routing. `AGENTS.md` carries
the standing rules and is loaded into every agent automatically.

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

A fourth was found late and is the sharpest: **Envoy applies route-level header mutations in
the router filter, after `ext_proc`**, so route-level identity injection never reached the
EPP and a profile labelled `hardened` was reading a client-supplied identity — the exact
forgery ADR-006 exists to close. The EPP is wired to Envoy via `ext_proc`, and the trust
boundary works because `envoy.filters.http.header_mutation` is placed as a real HTTP filter
**before** it. See §F-27.

---

## What ran where

The two-tenant BARRIER kind cluster stands up in **GitHub Actions CI on every push, in both
profiles** — `default` and `hardened` — running S-02 and FR-B-03 with it. That costs £0. A
reviewer who wants to run it locally instead can: see `docs/RUNBOOK-local.md`.

ATTEST cannot run on a development machine at all — batch invariance requires an NVIDIA GPU
of compute capability 8.0 or higher; AMD is untested upstream and CPU is unsupported. Every
ATTEST measurement comes from staged rented sessions on H100 and A40, six pods for roughly
**$2.00** in total, and each run's raw output is committed under `bench/results/`. The stub
engine (`tests/support/stub_engine.py`) is what made that cheap: the whole pipeline was
developed and tested with no GPU, so integration bugs surfaced before the meter started.

---

## The two risks the design carried

Both are closed.

- **RSK-01** — divergence might not have appeared at small model size. It did: 34 of 128
  distinct logprob vectors at temperature 0, and the invariance and cost numbers followed.
- **RSK-02** — the llm-d simulator might expose no client-observable routing signal. It does
  not. S-02 is **resolved** (ADR-011, CI run #12, n=402): latency AUC 0.5581 [0.5026, 0.6138],
  p=0.0425, which does not clear the pre-registered bar, against a positive control showing
  the EPP's prefix index matched on 402 of 404 lookups. The router had something to leak and
  the client could not see it. FR-B-03 was therefore rescoped to an operator-instrumented
  demonstration, and the attacker-observable oracle moved to **FR-B-09 on real vLLM**, which
  is still open.

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
