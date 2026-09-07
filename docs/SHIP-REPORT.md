# Ship report

**Date:** 2026-09-07 · **SHA at writing:** see `git log -1`
**Verdict: ATTEST ships. BARRIER does not yet, and the reason is stated rather than hidden.**

Phase 7 of the lifecycle. Its job is to say what is true, what is claimed, and
what is not — in a form a reviewer can check without trusting the author.

---

## 1. What is claimed, and what backs it

Every row traces to a run id in `bench/results/` carrying the git SHA that
produced it.

| Claim | Evidence | Confidence |
|---|---|---|
| Batched inference at temperature 0 is not reproducible | 34 of 128 distinct logprob vectors, H100 | **Measured** |
| vLLM's batch invariance reduces but does not eliminate it | 5 of 128 remain | **Measured** |
| Determinism costs 22.7% throughput on vLLM | 95% CI [0.741, 0.808], n=128/arm | **Measured, with interval** |
| Determinism costs 18.0% on SGLang, isolated from caching | D/B = 0.820× | **Measured, point estimate** |
| SGLang's deterministic mode *does* eliminate divergence | 1 of 128, cache on and off | **Measured** |
| `cache_salt` exists upstream and is unenforced | vLLM + llm-d source | **Verified by source read** |
| SGLang has the same unenforced gap, and `extra_key` is the wrong field | `sgl-project/sglang@30705c0` | **Verified by source read** |
| The tenant-salt plugin closes the routing-index channel | 22 Go tests against real llm-d | **Compiles, passes, and now runs in a live cluster — but its *effect* is unmeasured** |
| The proxy refuses unauthenticated callers | Run #13: `gateway answered: 401` | **Measured** |
| The proxy's injected identity reaches the plugin | — | **Claimed in run #13 and WITHDRAWN. Route-level header mutations are invisible to ext_proc (F-27); the EPP was reading the client's own header.** |
| No client-observable routing oracle exists on the simulator | ADR-011, CI run #12, n=402 | **Measured, with a positive control** |
| A routing-index leak exists to instrument | EPP prefix index: 402 of 404 lookups matched | **Measured** |
| The attack works against a client | — | **Not established, and ADR-011 says why: it rescopes to FR-B-09 on real vLLM.** |

The last row is the honest state of BARRIER and is why this report does not say
the project is finished.

## 2. What went wrong, and what caught it

Kept because a repository whose entire subject is verifiable claims does not get
to publish only its successes.

| # | Defect | How it was caught |
|---|---|---|
| 1 | The EPP plugin had never compiled — referenced a field that does not exist | Building it, after re-testing a limit I had asserted without testing |
| 2 | `ApplySalt` never salted the pre-tokenized path; "hardened" reported itself hardened while that surface leaked | Enumerating what the hasher actually reads |
| 3 | `return_token_ids` never sent; every receipt would have had no subject to bind | Reading vLLM's source before spending a GPU minute |
| 4 | `/server_info` wrong path, wrong gating, wrong nesting — the invariance refusal would never have fired | Same |
| 5 | Stage 2 would have run both arms against one engine | Wiring the job, before the meter started |
| 6 | **The guard against #5 had the bug it was written to prevent** — it read a stub-only endpoint, failed open, and produced an H100 result that was the opposite of the truth | A 32-trial cell finishing in **zero seconds** |
| 7 | The first "invariance fixes it" result was underpowered at 32 trials | Re-running at 128 |
| 8 | `up.sh` discarded the image reference `ko` produced, so the EPP deploy referenced an image nobody built | Reading the deploy path before the first CI run |
| 9 | **The chart never wired Envoy to the EPP** — no `ext_proc` filter existed, so the plugin could not run and the two profiles would have behaved identically | Reading the deploy path. Fixed; confirmed by CI run #6 |
| 10 | `ko`'s `kind.local` publisher cannot tag on a multi-node kind cluster | The first CI run that got that far |
| 11 | The EPP config had no `apiVersion`/`kind`, named `least-queue-filter` (which does not exist upstream), declared none of its `pluginRef`s, and listed a requestcontrol plugin as a scheduling one | Reading llm-d's own shipped configs |
| 12 | **S-02 returned ORACLE VIABLE on a millisecond counter**, twice — the refutation was three lines above it in the same output both times | Reading the run rather than the verdict |
| 13 | The ground-truth gate died on a 401 and reported nothing; then passed on a plugin-duration histogram that proved nothing | The gate's own output making no sense |
| 14 | **Route-level identity injection never reached the EPP** — Envoy applies route header mutations in the router filter, after ext_proc — so the "hardened" profile was reading a client-supplied identity, the exact forgery ADR-006 exists to close | An instrument that deliberately withholds the header under test |

**Thirteen of the fourteen were caught before or by a number that made no sense.**
The one that reached a published claim (#6/#7) was amended in place, with the
wrong run left in `bench/results/` and explained.

**Four of them — #6, both halves of #13, and #14 — were guards or reports that
contained the defect they were written to catch.** #14 is the sharpest: run #13's
writeup reported a passing trust boundary from a true observation (404 probes
served) and an inference that skipped one possibility (that the *client* supplied
the header). The correction is appended to that writeup rather than replacing it. That is the single most useful pattern this
project has surfaced about its own methods, and it is why the S-02 ground-truth
check ended up as tested code rather than a shell one-liner.

## 3. Gates

```
make check   ruff · ruff format · mypy strict · 287 pytest · Go build/vet/test (22)
```

Green. The Go gate fails in the cloud container only, because it invokes the
system Go which tries to fetch the pinned toolchain through a blocked proxy; on
a machine with normal egress it is correct as written (ADR-008).

## 4. What a reviewer should check first

1. **`bench/results/`** — five runs, including one that was wrong and one that
   was underpowered, each with the reason attached. This is the most
   load-bearing directory in the repository.
2. **`docs/design/decisions.md`** — ten ADRs, each with the options considered
   and the consequences accepted, several overturning the original brief.
3. **`docs/design/spikes/S-03-…`** — a decision rule fixed before the evidence
   was read, and a verdict that came back better than the hypothesis.
4. **`barrier/epp/plugin/plugin_test.go`** — tests that interrogate upstream
   rather than restate a list, so a dependency bump cannot silently reopen the
   channel.

## 5. What is not done

- **The mitigation's effect is unmeasured.** Both profiles now run in CI on
  every push and the hardened trust boundary demonstrably works (run #13), but
  the S-02 probe schedule buries the single cross-tenant event in 403
  same-tenant repeats, so the aggregate prefix hit ratio is identical under both
  — as it should be. **The two-profile diff that this project has promised since
  its requirements were written still does not exist.**
  `bench/results/hardened-run13-2026-09-07.md` states what FR-B-03's
  instrumented demonstration has to do instead, and why the obvious aggregate
  cannot do it.
- **No receipt has been signed against a real engine.** The pipeline is
  exercised end to end against the stub (`make attest-demo`, including a
  tamper-detection test); the GPU runs measured divergence and cost but did not
  emit receipts.
- **The cross-engine comparison is not controlled.** vLLM and SGLang ran under
  their own defaults. Two measurements, not an experiment.
- **A-05**, confidence intervals on the 2×2, SGLang's Triton backend, and the
  dependence of any of this on model size — all open, none load-bearing.

## 6. Cost

Six GPU pods, roughly **$2.00**. Every published number in this repository was
produced for about the price of a coffee, on hardware rented by the hour and
released the same day.
