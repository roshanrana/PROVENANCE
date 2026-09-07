# Execution Plan — PROVENANCE

**Status:** draft · **LLD:** `docs/design/03-lld.md` (approved 2026-08-29)
**Date:** 2026-08-29 · **50 tasks across 7 milestones**

---

## Milestones

| ID | Name | Demonstrates | Gate |
|---|---|---|---|
| **M0** | Guardrails + walking skeleton | One stub inference → raw cell → signed receipt → verified receipt → committed result, through the real pipeline and CI | `make check` green **and** `make attest-demo` green in CI |
| **M1** | ATTEST core | Real vLLM driver, matrix + ledger, statistics, Hub provenance, analysis — everything except the GPU run | `make check` + integration suite against stub engine; NFR-05 thresholds asserted |
| **M2** | ATTEST measured results | The staged GPU session executed, analysed, and written up | Committed raw output + figures regenerable by script; ATTEST writeup complete |
| **M3** | BARRIER foundation | kind cluster, two-tenant topology, custom EPP image, S-02 answered, threat model written | `make barrier-up` works from clean clone; S-02 verdict in `decisions.md` |
| **M4** | BARRIER mitigation | tenant-salt plugin closing both channels; hardened values; isolation cost measured | Plugin unit tests green; `values-hardened` diff reviewable; cost table committed |
| **M5** | BARRIER attack + results | Oracle, three attack variants, pre-registered statistics, writeup | Verdict published verbatim from `decide()`; BARRIER writeup complete |
| **M6** | Ship readiness | README, architecture doc, gate ladder, ship report | Ship report presented; go/no-go |
| **M7** | Impressive tier *(deferred)* | HF Space, Grafana dashboard, real-vLLM timing oracle | Gated behind M2 — does not compete with ATTEST MVP |

M0 is the walking skeleton: the thinnest end-to-end slice through the *real* architecture
(harness → ledger → engine interface → receipt → sign → verify → committed result → CI),
using a stub engine so it runs with no GPU and no cluster. Every later task inherits its
guardrails for free.

---

## Task table

Scheduling source of truth. `STATE.md` mirrors only the current wave.
Size: **S** ≤150 lines, **M** ≤400 lines, **L** = split candidate if it grows.
Env: **C** = cloud container · **R** = Roshan's machine · **G** = rented GPU.

| ID | Title | M | Wave | Depends on | Size | Env | Status |
|---|---|---|---|---|---|---|---|
| T-001 | Scaffold repo tree, uv workspace, pyproject | M0 | 1 | — | M | C | todo |
| T-002 | Python quality gates: ruff, mypy, pytest config | M0 | 2 | T-001 | S | C | todo |
| T-003 | Go module scaffold + golangci-lint for `barrier/epp` | M0 | 2 | T-001 | S | C | todo |
| T-006 | `common/runid.py` — run-id and manifest construction | M0 | 2 | T-001 | S | C | todo |
| T-008 | Stub vLLM engine test double | M0 | 2 | T-001 | M | C | todo |
| T-009 | `attest/receipt/schema.py` — frozen predicate types | M0 | 2 | T-001 | S | C | todo |
| T-004 | Single `make check` spanning both toolchains | M0 | 3 | T-002, T-003 | S | C | todo |
| T-007 | `attest/harness/ledger.py` — cells.jsonl state machine | M0 | 3 | T-006 | M | C | todo |
| T-010 | `attest/receipt/sign.py` — ed25519 + JCS canonicalisation | M0 | 3 | T-009 | M | C | todo |
| T-005 | GitHub Actions CI running `make check` | M0 | 4 | T-004 | S | C | todo |
| T-011 | `attest verify` CLI with full exit-code taxonomy | M0 | 4 | T-010 | M | C | todo |
| T-012 | Walking skeleton: `make attest-demo` end to end | M0 | 5 | T-005, T-007, T-008, T-011 | M | C | todo |
| T-013 | `common/stats/auc.py` — AUC + bootstrap CI | M1 | 6 | T-012 | M | C | todo |
| T-014 | `common/stats/permutation.py` | M1 | 6 | T-012 | S | C | todo |
| T-017 | `attest/harness/matrix.py` — pure matrix generation | M1 | 6 | T-012 | M | C | todo |
| T-019 | `attest/receipt/provenance.py` — Hub identity resolution | M1 | 6 | T-012 | M | C | todo |
| T-015 | `common/stats/decision.py` — Verdict, NFR-05 thresholds | M1 | 7 | T-013, T-014 | S | C | todo |
| T-016 | `common/stats/noise.py` — noise floor, `required_trials` | M1 | 7 | T-013 | M | C | todo |
| T-018 | `attest/harness/engine.py` — vLLM lifecycle + resolved config | M1 | 7 | T-017 | L | C | todo |
| T-020 | `attest verify --online` (exit 5, 6) | M1 | 7 | T-019 | S | C | todo |
| T-021 | `attest replay` | M1 | 8 | T-018, T-020 | M | C | todo |
| T-024 | `common/traces/replay.py` — published-trace workload | M1 | 8 | T-016 | M | C | todo |
| T-022 | Analysis: divergence table | M1 | 8 | T-017 | M | C | todo |
| T-023 | Analysis: cost estimates with CIs | M1 | 9 | T-015, T-022 | M | C | todo |
| T-025 | Stage-1 divergence-hunt runner | M1 | 9 | T-018, T-024 | M | C | todo |
| T-026 | Stage-2 measured-matrix runner | M1 | 9 | T-025 | M | C | todo |
| T-027 | GPU session rehearsal + time-budget validation | M2 | 10 | T-026 | M | C | todo |
| T-028 | Execute staged GPU session | M2 | 11 | T-027 | L | **G** | todo |
| T-029 | Analyse results, commit figures | M2 | 12 | T-028 | M | C | todo |
| T-030 | APC × invariance secondary experiment | M2 | 12 | T-028 | M | C | todo |
| T-031 | ATTEST writeup | M2 | 13 | T-029, T-030 | M | C | todo |
| T-032 | kind wrapper over upstream `Makefile.kind.mk` | M3 | 6 | T-001 | M | **R** | todo |
| T-033 | Default topology values: 2 tenants, 2 sim pods | M3 | 7 | T-032 | M | **R** | todo |
| T-034 | Custom EPP module + `main.go` + ko build (no plugin logic) | M3 | 7 | T-003 | M | C | todo |
| T-035 | **Execute S-02 spike**, record verdict | M3 | 8 | T-033, T-034 | M | **R** | todo |
| T-036 | `docs/threat-model.md` | M3 | 8 | T-035 | M | C | todo |
| T-037 | tenant-salt plugin: salt derivation + typed config | M4 | 9 | T-034 | M | C | todo |
| T-038 | tenant-salt plugin: seed EPP prefix hash chain | M4 | 10 | T-037 | M | C | todo |
| T-039 | tenant-salt plugin: rewrite outbound `cache_salt` (ADR-007) | M4 | 10 | T-037 | M | C | todo |
| T-040 | Proxy header-stripping config (ADR-006) | M4 | 10 | T-033 | S | **R** | todo |
| T-041 | `values-hardened.yaml` + committed rendered diff | M4 | 11 | T-038, T-039, T-040 | S | **R** | todo |
| T-042 | Isolation cost: hit rate and TTFT p50/p99 | M4 | 12 | T-041 | M | **R** | todo |
| T-043 | Oracle implementation | M5 | 12 | T-035, T-041 | L | **R** | todo |
| T-044 | Attack variants: omission, forgery, negligence | M5 | 13 | T-043 | M | **R** | todo |
| T-045 | Statistical evaluation, publish Verdict verbatim | M5 | 13 | T-015, T-044 | M | C | todo |
| T-046 | BARRIER writeup | M5 | 14 | T-042, T-045 | M | C | todo |
| T-047 | README (FR-R-02) | M6 | 14 | T-031, T-046 | M | C | todo |
| T-048 | `docs/architecture.md` | M6 | 14 | T-036 | M | C | todo |
| T-049 | Gate ladder: audits, coverage, secrets scan | M6 | 14 | T-005 | M | C | todo |
| T-050 | `docs/ship-report.md` | M6 | 15 | all | M | C | todo |

**Requirement coverage check.** Every FR maps to at least one task, and every task cites at
least one requirement in its pack. Verified at this gate: FR-A-01→T-025/T-028,
FR-A-02→T-017, FR-A-03→T-026, FR-A-04→T-023, FR-A-05→T-009/T-010/T-019,
FR-A-06→T-011/T-020, FR-A-07→T-021, FR-A-08→T-030, FR-A-09→T-007/T-026,
FR-B-01→T-036, FR-B-02→T-032/T-033/T-040, FR-B-03→T-043, FR-B-04→T-045,
FR-B-05→T-037/T-038/T-039, FR-B-06→T-044, FR-B-07→T-042, FR-B-08→T-039/T-046,
FR-B-09→M7, FR-R-01→T-012/T-032, FR-R-02→T-047, FR-R-03→T-031/T-046,
FR-R-04→T-029, FR-R-05→T-036/T-048, FR-R-06→T-047, FR-R-07/08→M7.

---

## Dependency notes

Only the non-obvious edges.

- **T-012 → T-008.** The walking skeleton runs against the stub engine, not vLLM. This is
  deliberate: M0 must be runnable in CI with no GPU, so the engine *interface* is exercised
  end to end while the real driver (T-018) is still unwritten.
- **T-018 → T-017.** The engine driver consumes matrix cells; the matrix is a pure function
  and is testable first, so a bug in scheduling never masquerades as an engine bug.
- **T-035 → T-034.** The S-02 spike needs a deployable EPP image even though the plugin has
  no logic yet — the spike measures the *stock* configuration, and building the image first
  proves the ko path before plugin work depends on it.
- **T-043 → T-035.** The oracle's score function is LLD §4.4, which is unfrozen until the
  spike returns. **T-043's pack cannot be written in full until T-035 completes.**
- **T-039 → ADR-007.** Rewriting the outbound body is a separate task from seeding the hash
  chain (T-038) because they touch different points in the request lifecycle and can fail
  independently. Splitting them keeps each diff small enough to review.
- **T-045 → T-015.** The statistical verdict must come from the frozen `decide()`, not from
  analysis-local code. Enforced by the pack's file scope: T-045 may not modify `common/stats`.

---

## Wave schedule

A wave is a set of tasks with satisfied dependencies and disjoint file scopes.

```
Wave  1: T-001                                    (scaffold — must land alone)
Wave  2: T-002  T-003  T-006  T-008  T-009
Wave  3: T-004  T-007  T-010
Wave  4: T-005  T-011
Wave  5: T-012                                    ── M0 GATE ──
Wave  6: T-013  T-014  T-017  T-019  T-032
Wave  7: T-015  T-016  T-018  T-020  T-033  T-034
Wave  8: T-021  T-022  T-024  T-035  T-036
Wave  9: T-023  T-025  T-026  T-037               ── M1 GATE ──
Wave 10: T-027  T-038  T-039  T-040
Wave 11: T-028  T-041                             (T-028 is the GPU session)
Wave 12: T-029  T-030  T-042  T-043
Wave 13: T-031  T-044  T-045                      ── M2 / M4 GATES ──
Wave 14: T-046  T-047  T-048  T-049
Wave 15: T-050                                    ── SHIP GATE ──
```

**BARRIER runs in parallel from Wave 6.** D-04 says ATTEST ships first, and it does — M2
completes at Wave 13 — but BARRIER's cluster work (T-032, T-033, T-035) has no file-scope
overlap with ATTEST and runs on a different machine, so serialising them would waste weeks
for no benefit. What "ATTEST first" buys is that if time runs short, M3–M5 can be cut
without leaving a half-finished repo.

**Environment interleaving.** Waves 6–13 mix cloud-container tasks with tasks that need
Roshan's machine (**R**) or the GPU (**G**). Those are the handoff points. Every **R** and
**G** task's pack must therefore be a self-contained script that records its own output —
required by requirements §6.4 and checked at this gate. T-028, T-035, T-042 and T-043 are
the four where this matters most.

---

## Gate map

| Milestone | Gate level | What runs |
|---|---|---|
| M0 | Per-task + milestone | `make check`; `make attest-demo`; both green in CI |
| M1 | Milestone | `make check`; integration suite vs stub engine; NFR-05 threshold assertions; coverage ≥80% on `common/stats` and `attest/receipt` |
| M2 | Milestone | Every figure regenerable from committed raw output; manifest completeness; no headline number over an incomplete matrix |
| M3 | Milestone | `make barrier-up` from clean clone; S-02 verdict recorded in `decisions.md` before any oracle code exists |
| M4 | Milestone | Go unit tests incl. fail-closed and override-not-merge; rendered Helm diff reviewed |
| M5 | Milestone | Verdict published verbatim; pre-registration date precedes results date in git history |
| M6 | Pre-ship | `uv pip audit`, `govulncheck`, secrets scan, coverage report, full docs review |

**One gate has an unusual check.** At M5, the git history must show the pre-registered
thresholds (T-015) committed *before* the results (T-044). If that ordering does not hold,
the pre-registration is worthless and the claim must be weakened. This is checked, not
assumed.

---

## Top risks carried from the HLD

1. **RSK-01 — no divergence at 0.5B.** T-028's Stage 1 is a human decision point inside a
   scripted run. If nothing diverges, ATTEST's centre of gravity shifts to receipts and the
   APC finding (T-030), and the negative result is published (NFR-17). Requirements are
   written so this outcome still ships.
2. **RSK-02 — no client-observable signal on the simulator.** T-035 answers it. The decision
   rule is already written down (LLD §7) so the result cannot be rationalised after the
   fact. Worst case rescopes FR-B-03 to an instrumented demonstration and moves the
   attacker-observable oracle to M7.
3. **T-043 is the largest carried unknown.** Its pack cannot be completed until T-035
   returns, so it is deliberately marked **L** and scheduled late. If the spike says the
   oracle is not viable, T-043 and T-044 change shape entirely — that is a plan amendment,
   recorded in `decisions.md`, not improvisation.

Secondary: upstream API drift (R-4) is mitigated by pinning and by `make check` compiling
against the pin; CI time (R-6) is watched from T-005 onward, and the demo job splits from
`check` if the 5-minute budget slips.

---

## Pack coverage

Full packs written for **Waves 1 and 2**: T-001, T-002, T-003, T-006, T-008, T-009.
Later packs are refined at each milestone boundary, per the planning reference — details
learned in M0 routinely improve them, and paying for detail that will be rewritten is waste.
The task table above is complete from day one regardless.

Browse packs at `docs/tasks/`.
