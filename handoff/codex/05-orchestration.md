# 05 — Orchestration Runbook

**Status:** draft · **Date:** 2026-08-29
**Governs:** Phase 5 (implementation loop) and every later phase run with multiple agents.

How PROVENANCE is built with an Opus orchestrator directing Sonnet workers, and how context
is kept small enough that quality does not decay across 50 tasks.

---

## 1. Roles and their settings

| Role | Model | Effort | Why |
|---|---|---|---|
| **Orchestrator** (main session) | `opus` | `high` | Owns the plan, writes packs, merges, runs gates, talks to Roshan. Never implements. |
| `worker` | `sonnet` | `medium` | Executes one pack. The pack already contains the thinking; this is execution. |
| `verifier` | `sonnet` | `medium` | Fresh-eyes judgment on one diff against its criteria. |
| `verifier-critical` | `opus` | `high` | Contracts, statistics, cryptography, the security plugin — where a subtle error silently corrupts a result. |
| `spike` | `opus` | `high` | Investigations whose output freezes contracts. Getting one wrong costs far more than the tokens. |

Files: `.claude/settings.json`, `.claude/agents/{worker,verifier,verifier-critical,spike}.md`.

### The one configuration trap

**Do not set `CLAUDE_CODE_SUBAGENT_MODEL`.** Subagent model resolution is
`env var → per-invocation param → frontmatter → main model`. The environment variable sits
*above* frontmatter, so setting it silently flattens every agent to one model and quietly
discards the split above. Leave it unset and let each agent's frontmatter decide.

`effort` is per-agent frontmatter only — there is no per-invocation effort override. That is
why `verifier-critical` is a separate agent rather than a flag on `verifier`.

---

## 2. Why this saves context (the actual mechanism)

A subagent is **not** a fork. A non-fork subagent starts with: its own system prompt, the
dispatch message, `CLAUDE.md`, and a git status snapshot. It **never** receives the parent's
conversation history.

That single property is the whole design. A worker reads five files, writes a diff, and
churns through tool output — and none of that ever enters the orchestrator's context. Only
its closing summary returns. Fifty tasks of exploration, test output, and stack traces stay
where they happened.

The corollary matters as much: **`CLAUDE.md` is loaded into every subagent, so it is a tax
paid ~150 times.** Ours is deliberately short and rule-dense. Project background lives in
`docs/design/`, which agents read by pointer, on demand. A 400-line CLAUDE.md would cost more
across this project than most individual tasks.

Six levers, in rough order of impact:

1. **Isolation** — worker exploration never reaches the orchestrator. Everything else is a
   refinement of this.
2. **Dispatch is a pack path and nothing else.** If a pack is not sufficient to launch from,
   fix the pack. That defect would otherwise be paid in every future session that reads it.
3. **`isolation: worktree` on `worker`** — each worker gets its own git worktree, so a wave's
   parallel tasks physically cannot collide. File-scope discipline becomes enforced rather
   than merely promised.
4. **`maxTurns`** — a hard circuit breaker (40 for workers, 20–30 elsewhere). A runaway agent
   stops burning tokens without needing anyone to notice.
5. **Tool allowlists** — `verifier` gets no write tools at all, which is both a context
   saving and a structural guarantee it cannot "helpfully" fix what it is judging.
6. **No preloaded skills on workers.** The `skills:` frontmatter field injects *full* skill
   text at startup. The orchestrator needs the lifecycle skill; workers need their pack,
   which already distils it.

---

## 3. The loop

Per task:

```
orchestrator: pick next unblocked task in wave; confirm pack is fresh
      ↓
   worker  ──────────────►  diff + Handoff notes    [sonnet / medium]
      ↓
  verifier ──────────────►  per-criterion PASS/FAIL [sonnet / medium]
      ↓                     (verifier-critical for contract/stats/crypto/plugin tasks)
orchestrator: merge · run gates · update STATE.md + task table · commit "T-###: …"
```

Per wave:

```
dispatch wave (parallel) → collect → merge task-by-task, fast gates after each
→ milestone gate if the wave closes one → digest to Roshan → open next wave
```

Merging task-by-task rather than wave-at-once means a breakage is attributable to one task
instead of requiring a wave-sized bisect.

**Do not parallelise for its own sake.** Dispatch and merge overhead exceeds the gain below
about three medium tasks. From the plan: waves 1 and 5 are single tasks — run them inline in
the orchestrator. Waves 2, 6, 7, 8 have 5–6 tasks each and are where fan-out actually pays.

---

## 4. Wave dispatch, concretely

Wave 2 is five tasks with pairwise-disjoint file scopes:

```
Agent(worker)  "Implement docs/tasks/T-002-python-gates.md"
Agent(worker)  "Implement docs/tasks/T-003-go-scaffold.md"
Agent(worker)  "Implement docs/tasks/T-006-runid.md"
Agent(worker)  "Implement docs/tasks/T-008-stub-engine.md"
Agent(worker)  "Implement docs/tasks/T-009-receipt-schema.md"
```

That is the entire dispatch message. No context, no background, no explanation — the pack
carries all of it, and anything extra is context the orchestrator pays for and the worker
does not need.

**One writer per file, ever.** If two ready tasks overlap on a file, serialise them or
re-split the plan. Never run them concurrently and hope.

Verification routing:

| Task | Verifier |
|---|---|
| T-002, T-003, T-006, T-008 | `verifier` |
| **T-009** (frozen receipt schema) | `verifier-critical` |

Wave 8 dispatches `spike` for T-035, not `worker` — its deliverable is a decision in
`decisions.md`, and no oracle code may exist before that decision does.

---

## 5. Failure handling

**Two strikes, per worker per task.** Validation fails → fix and re-run once → fails again →
stop, write findings and hypotheses into the pack, mark `blocked`, return.

The orchestrator then chooses: re-scope the task, fix the pack, schedule a spike, or escalate
to Roshan. It does **not** relaunch the same worker at the same task — that is precisely how
token-burning loops start, and a second failure usually indicts the pack or the design rather
than the worker.

A worker that goes silent or badly overruns is treated as failed. Discard its partial diff
unless gates pass on it; never merge unverified partial work.

**Repeated failures across different tasks in one area signal a design defect, not worker
error.** The orchestrator raises it as an LLD issue at the next gate rather than grinding.

---

## 6. What Roshan sees

A compact digest at each wave and milestone boundary — never a transcript:

- Tasks completed, one line of outcome each
- Gate results
- Deviations recorded, with the `decisions.md` entry
- Blockers and **batched** questions
- What the next wave contains

Questions are batched to boundaries. A mid-task question means the task is marked `blocked`
with the question written into its pack, and work moves to the next unblocked task. The one
exception, always asked immediately: anything irreversible or that spends money — which in
this project means **starting the rented GPU session (T-028)**.

You should never need to read a diff to know where the project stands.

---

## 7. Prerequisites before the first dispatch

1. **Push the repo to GitHub.** Cloud sessions work from a remote, and neither agent
   environment has `gh` or a configured git identity — so the first push is yours.
2. **Land these files:** `.claude/settings.json`, `.claude/agents/*.md`, `CLAUDE.md`.
3. **Confirm `CLAUDE_CODE_SUBAGENT_MODEL` is unset** in the environment (§1).
4. **Re-verify `docs/design/00-upstream-findings.md`** — NFR-19 requires it at the start of
   Phase 4, and both dependencies are beta.
5. **Wave 1 (T-001) runs inline**, not dispatched. It creates the tree every other task
   writes into, and it is a single task.

---

## 8. What stays with Roshan

Cloud agents cannot reach the kind cluster or the rented GPU. From the plan, these tasks are
yours to execute: **T-032, T-033, T-035, T-040, T-041, T-042, T-043, T-044** (cluster) and
**T-028** (GPU).

Their packs are therefore written as self-contained scripts that record their own output into
`bench/results/`, so the orchestrator can read the result without having watched the run.
That constraint was set at the Phase 3 gate and is checked when each of those packs is
finalised. It is the difference between a handoff and a conversation.
