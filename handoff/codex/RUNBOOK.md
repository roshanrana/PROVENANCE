# 06 — Codex Build Runbook

**Status:** draft · **Date:** 2026-08-29
**Governs:** Phase 4 onward, run with OpenAI Codex.

How PROVENANCE gets built with Codex CLI: roles, profiles, the wave loop, and how context is
kept small enough that quality does not decay across 50 tasks.

Companion to `05-orchestration.md`, which describes the same division of labour for Claude
Code. The roles are identical; only the mechanism differs.

---

## 1. How Codex differs, and what that changes

Codex has **no per-agent frontmatter** for model and reasoning effort — there is no
equivalent of a `.claude/agents/*.md` file that binds a role to a model. What it has instead:

| Need | Codex mechanism |
|---|---|
| Standing project rules, auto-loaded | `AGENTS.md` at the git root |
| Per-role reasoning effort | **Named profiles** in `~/.codex/config.toml` |
| Per-role behaviour | **Role prompt files** in `codex/roles/`, prepended to the dispatch |
| Structural isolation | `sandbox_mode` per profile — read-only for verifiers |
| Context isolation between tasks | **A fresh session per task.** This is manual, and it matters. |

Codex does have a `multi_agent` feature (`codex features enable multi_agent`), but its
behaviour is not documented well enough to build a process on. **This runbook does not
depend on it.** Roles here are separate `codex` invocations with different profiles — which
is explicit, debuggable, and works today. If you enable `multi_agent` later, the role prompts
transfer unchanged.

---

## 2. Roles and profiles

| Role | Profile | Effort | Sandbox | Purpose |
|---|---|---|---|---|
| **Orchestrator** | `orchestrator` | high | workspace-write | Owns the plan. Picks tasks, refreshes packs, merges, runs gates, updates `STATE.md`. **Never implements.** |
| `worker` | `worker` | medium | workspace-write | Executes one pack. The pack contains the thinking; this is execution. |
| `verifier` | `verifier` | medium | **read-only** | Fresh-eyes judgment on one diff. |
| `verifier-critical` | `verifier-critical` | xhigh | **read-only** | Contracts, statistics, cryptography, the security plugin. |
| `spike` | `spike` | high | workspace-write | Investigations whose output freezes contracts. |

Setup: merge `codex/config.toml.example` into `~/.codex/config.toml`.

**Read-only for verifiers is deliberate.** It is not a precaution — it is what makes the role
real. A verifier that *can* fix what it is judging eventually will, and then nothing
independent has judged the fix.

---

## 3. Why this keeps context small

Codex gives no automatic context isolation between roles, so **it has to be created by
starting a fresh session per task**. That single discipline does most of the work: a worker's
exploration, test output, and stack traces stay in that worker's session and never
accumulate in the orchestrator's.

Six levers, in rough order of impact:

1. **One session per task, always.** Never continue a worker's session into the next task.
   Never let the verifier inherit the worker's session — that would defeat the role outright.
2. **Dispatch is a pack path and nothing else.** Not background, not a summary, not an
   explanation. The pack carries all of it. If a pack is not sufficient to launch from, fix
   the pack — that defect would otherwise be paid by every future reader.
3. **`AGENTS.md` is loaded into every session**, so it is a tax paid ~150 times over this
   project. Ours is deliberately short and rule-dense. Background lives in `docs/design/`,
   read by pointer. A 400-line AGENTS.md would cost more across this build than most
   individual tasks.
4. **`web_search = "disabled"` on the worker profile.** A worker needing the web is a pack
   defect, and searching is a large, silent context cost.
5. **Read-only sandbox on verifiers** — both a saving and a structural guarantee.
6. **Fixed read order:** `STATE.md` → pack → in-scope files. Nothing else, ever. Repo-wide
   exploration is the largest avoidable cost in agentic development, and `STATE.md` exists so
   it is never necessary.

---

## 4. The loop

Per task — each arrow is a **new session**:

```
orchestrator ──► pick next unblocked task in wave; confirm pack is fresh
     │
     ├─► codex --profile worker    + codex/roles/worker.md    + "Implement docs/tasks/T-002-….md"
     │        └──► diff + Handoff notes
     │
     ├─► codex --profile verifier  + codex/roles/verifier.md  + "Verify T-002 against its pack"
     │        └──► per-criterion PASS/FAIL
     │
     └─► orchestrator: merge · run gates · update STATE.md + task table · commit "T-002: …"
```

Per wave:

```
dispatch wave → collect → merge task-by-task, fast gates after each
→ milestone gate if the wave closes one → digest to Roshan → open next wave
```

Merging task-by-task rather than wave-at-once means a breakage is attributable to one task
instead of requiring a wave-sized bisect.

**Do not parallelise for its own sake.** Dispatch and merge overhead exceeds the gain below
about three medium tasks. Waves 1 and 5 are single tasks — run them inline. Waves 2, 6, 7 and
8 carry 5–6 tasks each, and that is where fan-out pays.

---

## 5. Wave 2, concretely

Five tasks, pairwise-disjoint file scopes, five separate sessions:

```bash
codex --profile worker   # T-002  docs/tasks/T-002-python-gates.md
codex --profile worker   # T-003  docs/tasks/T-003-go-scaffold.md
codex --profile worker   # T-006  docs/tasks/T-006-runid.md
codex --profile worker   # T-008  docs/tasks/T-008-stub-engine.md
codex --profile worker   # T-009  docs/tasks/T-009-receipt-schema.md
```

Each dispatch is `codex/roles/worker.md` followed by one line naming the pack. Nothing more.

**One writer per file, ever.** If two ready tasks overlap on a file, serialise them or
re-split the plan. Never run them concurrently and hope. Because Codex has no worktree
isolation equivalent, run parallel workers **in separate git worktrees or clones** — or run
the wave sequentially. Sequential is slower and perfectly safe; concurrent writers to one
tree is neither.

Verification routing for this wave:

| Task | Profile |
|---|---|
| T-002, T-003, T-006, T-008 | `verifier` |
| **T-009** (frozen receipt schema) | `verifier-critical` |

Wave 8 dispatches `spike` for T-035, not `worker` — its deliverable is a decision in
`decisions.md`, and no oracle code may exist before that decision does.

---

## 6. Failure handling

**Two strikes, per worker per task.** Validation fails → fix and re-run once → fails again →
stop, write findings and hypotheses into the pack, mark `blocked`, return.

The orchestrator then chooses: re-scope the task, fix the pack, schedule a spike, or escalate
to Roshan. It does **not** relaunch the same worker at the same task. That is precisely how
token-burning loops start, and a second failure usually indicts the pack or the design rather
than the worker.

A worker that goes silent or badly overruns is treated as failed: discard the partial diff
unless gates pass on it. Never merge unverified partial work.

**Repeated failures across different tasks in one area signal a design defect, not worker
error.** Raise it as an LLD issue at the next gate rather than grinding.

---

## 7. What Roshan sees

A compact digest at each wave and milestone boundary — never a transcript: tasks completed
with one-line outcomes, gate results, deviations with their `decisions.md` entry, blockers
and **batched** questions, and what the next wave contains.

Questions batch to boundaries. A mid-task question means marking the task `blocked` with the
question written into its pack, then moving to the next unblocked task. One standing
exception, asked immediately: anything irreversible or that spends money — in this project,
**starting the rented GPU session (T-028)**.

You should never need to read a diff to know where the project stands.

---

## 8. Before the first dispatch

1. **Merge `codex/config.toml.example`** into `~/.codex/config.toml`; confirm
   `codex --profile worker` resolves.
2. **`git init`, commit, and push** to your remote.
3. **Re-verify `docs/design/00-upstream-findings.md`** and update its date stamp — NFR-19
   requires it, and both dependencies are beta. Do this at `spike` or `orchestrator` effort,
   not `worker`.
4. **Wave 1 (T-001) runs inline** — a single task creating the tree everything else writes
   into.
5. Decide **sequential or worktree-parallel** for Wave 2 (§5) before dispatching it.

---

## 9. What stays with Roshan

Codex cannot reach the kind cluster or the rented GPU. From the plan, these are yours to
execute: **T-032, T-033, T-035, T-040, T-041, T-042, T-043, T-044** (cluster) and **T-028**
(GPU).

Their packs are written as self-contained scripts that record their own output into
`bench/results/`, so the orchestrator reads the result without having watched the run. That
constraint was set at the Phase 3 gate and is checked when each of those packs is finalised.
It is the difference between a handoff and a conversation.
