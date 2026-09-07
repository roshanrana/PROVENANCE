# STATE

Living ledger for PROVENANCE. **This file is the single source of truth for where the
project is.** Read it first in every session. Do not begin a session with a repo-wide
crawl or `git log` archaeology — this file exists so that is never necessary.

---

## Now

- **Phase:** 4 — Guardrails · **design phases 0–3 complete and approved**
- **Status:** Execution plan **approved 2026-08-29**. Build handed off to **OpenAI Codex** —
  see `docs/design/06-codex-runbook.md`. `AGENTS.md`, `START-HERE.md`, `codex/` in place.
  No application code written yet.
- **Blocked on:** nothing. Ready for Wave 1.
- **Next:** re-verify `00-upstream-findings.md` (NFR-19), then **T-001 inline**, then Wave 2

## Next

1. Phase 4 — Wave 1 is **T-001 alone** (scaffold), then wave 2: T-002, T-003, T-006,
   T-008, T-009. Re-verify `00-upstream-findings.md` first (NFR-19). Run via
   `codex --profile orchestrator`; see `docs/design/06-codex-runbook.md`.
2. **T-035 runs the S-02 spike** (wave 8, Roshan's machine). Its verdict must be in
   `decisions.md` before any oracle code exists — T-043's pack cannot be completed until then.
3. M0 gate at wave 5: `make check` **and** `make attest-demo` green in CI.

---

## Pending spikes

These resolve by reading source or running code, not by more design discussion. They are
scheduled into Phase 2 and gate the LLD.

| ID | Question | Resolves | Blocks | Status |
|---|---|---|---|---|
| S-01 | llm-d EPP plugin registration mechanism. Confirms A-05. | Read `llm-d-router` source | FR-B-05 contracts | **RESOLVED — see F-02. Out-of-tree module works; no fork (ADR-002).** |
| S-02 | What routing signal is observable to an ordinary tenant caller on the simulator, given TTFT is unusable there. Confirms A-04, retires RSK-02. | Stand up the topology, probe as a tenant | FR-B-03, whole BARRIER MVP | **open — highest-priority spike** |
| S-03 | Whether the approximate scorer's prefix index is scoped across tenants. Confirms A-03. | Read source | Threat model FR-B-01 | **RESOLVED — see F-01. Changed FR-B-05.** |
| S-04 | Does `cache_salt` propagate to vLLM's own prefix cache, or only the EPP index? Confirms A-09. | Read vLLM source | Scope of FR-B-08 | **RESOLVED — yes. See F-03. Strengthens the mitigation (ADR-007).** |
| S-05 | Can the proxy strip client-supplied identity headers? Confirms HLD §8.1 trust boundary. | Read source | FR-B-02, R-5 | **RESOLVED in mechanism — strip at proxy + fail closed (ADR-006).** |

---

## F-01 — `cache_salt` already exists, and is client-supplied *(2026-08-29)*

Read from `llm-d-router` source at `pkg/epp/framework/plugins/requestcontrol/dataproducer/prefixhash/hashing.go`.
The prefix block-hash chain is seeded with:

```go
h := xxhash.New()
h.Write([]byte(request.TargetModel))              // model scoping
if cacheSalt := ...CacheSalt; cacheSalt != "" {   // optional
    h.Write([]byte(cacheSalt))
}
```

`CacheSalt` is an **optional, client-supplied JSON request field** —
`CacheSalt string \`json:"cache_salt,omitempty"\`` in
`pkg/epp/framework/interface/requesthandling/types.go`, parsed straight from the
request body, mirroring vLLM's `cache_salt` API extension.

**Consequences, all of which sharpen the project rather than weaken it:**

1. Index is scoped by **model only** by default. Two tenants on the same model share
   one prefix namespace. The default posture leaks, as hypothesised (A-03 confirmed).
2. The isolation primitive **already exists** — so BARRIER must not claim to invent it.
   Claiming novelty here would be caught instantly and would discredit the repo.
3. The real gap is that the salt is **caller-controlled and unauthenticated**: an
   attacker simply omits it; an honest tenant who forgets it is unprotected; and
   nothing binds a salt to a tenant identity, so a leaked or guessed salt is replayable.

**Revised FR-B-05:** the contribution is no longer "implement salted prefix hashing."
It is **bind the cache salt to authenticated tenant identity at the gateway, so it
cannot be omitted, forged, or replayed** — making an existing opt-in knob safe by
default. Smaller plugin, stronger and more defensible security argument, and squarely
within the "configuration and threat-model gap in the default deployment posture"
framing that NFR-18 requires.

**Also:** `llm-d-router` ships `Makefile.kind.mk` — upstream kind-based dev cluster
tooling. Phase 4 should build on it rather than hand-rolling a cluster.

---

## F-02 — out-of-tree plugins work; no fork needed *(2026-08-29)*

From `pkg/epp/framework/interface/plugin/registry.go` and `cmd/epp/runner/runner.go`:

```go
type FactoryFunc func(name string, parameters *json.Decoder, handle Handle) (Plugin, error)
func Register(pluginType string, stability StabilityLevel, factory FactoryFunc)  // exported
var Registry = map[string]FactoryFunc{}                                          // exported
func NewRunner() *Runner ; func (r *Runner) Run(ctx context.Context) error       // exported
```

`Registry` is a package-level exported map, so **any package can call `Register` from its
`init()`**. Our own tiny Go module can blank-import our plugin package and then run
upstream's runner unmodified — a custom EPP *image*, not a fork. See ADR-002.

Also confirmed: several shipped scheduling plugins read request headers
(`headerlabelaffinity`, `headerprofile`, `sessionaffinity`), so **tenant identity carried in
a header reaches plugin code at scheduling time**. This substantially de-risks RSK-05 —
the mitigation can live in the EPP as designed, provided the proxy strips the client's
version of that header (now spike S-05).

---

## F-03 — `cache_salt` reaches vLLM's engine cache too *(2026-08-29)*

vLLM's prefix-caching design doc: `cache_salt` is shipped, and is "injected into the hash of
the first block"; each block hash is `hash(parent_hash, block_tokens, extra_hashes)` where
extra hashes include "cache salts to isolate caches in multi-tenant environments."
Parent-hash chaining carries it to every downstream block.

So **one derived salt can close both channels** — the EPP routing index and the engine's real
KV cache — provided the plugin rewrites the outbound request body's `cache_salt`. That is
now a contractual obligation (LLD §4.3, ADR-007), and FR-B-08's residual shrinks accordingly.

---

## Key context (so it never has to be re-derived)

- **ATTEST cannot run on the dev machine.** Batch invariance needs NVIDIA SM ≥ 8.0. The
  Ryzen box does development, analysis and all of BARRIER's simulator work only.
- **One GPU session, 4–6 h**, staged: ~90 min divergence hunt → decision point → ~2.5 h
  measured matrix. See requirements §7.1.
- **The simulator does not vary TTFT on cache hit vs miss.** Settled constraint (D-01), not
  a bug to route around.
- **BARRIER's prior art is PrefixWall (arXiv 2603.10726).** Cite it, position against it.
- **Highest project risk is RSK-01:** divergence may not appear at 0.5B. Requirements are
  written so either outcome ships.

---

## Current wave

**Wave 1 (on approval): T-001** — scaffold repo tree and uv workspace. Lands alone; every
other task modifies files inside that tree.

Then **Wave 2: T-002, T-003, T-006, T-008, T-009** — disjoint file scopes, parallelisable.

Full table: `docs/design/04-execution-plan.md`. Packs: `docs/tasks/`.

---

## Task log

Append one line per completed task. Newest last.

| Date | ID | Task | Outcome |
|---|---|---|---|
| 2026-08-28 | — | Upstream verification of vLLM batch invariance and llm-d | `docs/design/00-upstream-findings.md`. Three brief corrections: sim TTFT gap, APC non-composition, PrefixWall prior art. |
| 2026-08-28 | — | Phase 0 intake | 11 decisions recorded (D-01…D-11) in `01-requirements.md` §2. |
| 2026-08-28 | — | Requirements drafted | `docs/design/01-requirements.md`. Awaiting gate. |
| 2026-08-29 | — | MCP registry survey | No connector worth adding. Registry has no GitHub / Kubernetes / Grafana / GPU-cloud entry; local tooling is strictly better for all of them. |
| 2026-08-29 | — | Cloned `llm-d-router` in cloud container | Go 1.24.7 + git + network present, so source reads and plugin builds happen here; only cluster runs need Roshan's machine. Produced F-01. |
| 2026-08-29 | — | Requirements v0.2 | 7 amendments folded in. FR-B-05 rewritten per F-01; HF provenance (D-12); Space + Grafana added as impressive tier; execution split recorded (§6.4); RSK-05 added. Docker Desktop confirmed → A-07 resolved. |
| 2026-08-29 | — | **Phase 0 gate PASSED** | Requirements v0.2 approved by Roshan. |
| 2026-08-29 | — | **Phase 1 gate PASSED** | HLD + 11 stack recommendations approved by Roshan. |
| 2026-08-29 | — | Spikes S-04, S-05 resolved from source | S-04 → ADR-007 (salt must reach the engine). S-05 → ADR-006 (strip at proxy, fail closed). S-02 narrowed: `served` header is stripped from responses, so the obvious signal is ruled out. |
| 2026-08-29 | — | **Phase 2 gate PASSED** | LLD approved by Roshan; contracts §4.1–4.5 frozen. |
| 2026-08-29 | — | **Phase 3 hard gate PASSED** | Execution plan approved by Roshan. Implementation may begin. |
| 2026-08-29 | — | Codex handoff packaged | `AGENTS.md`, `START-HERE.md`, `codex/config.toml.example`, `codex/roles/*` (worker, verifier, verifier-critical, spike), `docs/design/06-codex-runbook.md`. Claude Code equivalents retained at `docs/design/claude-config/` + `05-orchestration.md`. |
| 2026-08-29 | — | Execution plan written | `docs/design/04-execution-plan.md` — 50 tasks / 7 milestones / 15 waves; full packs for waves 1–2 in `docs/tasks/`. Awaiting hard gate. |
| 2026-08-29 | — | LLD written | `docs/design/03-lld.md` — repo layout, contracts §4.1–4.5 frozen, error taxonomy, test strategy, S-02 spike spec. §4.4 unfrozen pending S-02. |
| 2026-08-29 | — | HLD written | `docs/design/02-hld.md` — 8 components, 4 critical flows, 11 stack recommendations. `decisions.md` opened with ADR-001…005. Produced F-02 (S-01 resolved). Awaiting Phase 1 gate. |

---

## Decisions

Full log with rationale: `docs/design/decisions.md` (created in Phase 1).
Intake decisions D-01 … D-11 are recorded in `01-requirements.md` §2 and are settled —
reopening any of them is a plan change requiring a `decisions.md` entry.

---

## Blockers

None beyond the Phase 0 gate.

---

## Deviations

None.

---

## Session 2026-09-07 — amendment A-01 (SGLang), accepted and partly executed

### Findings

- **F-07 — the tenant-salt plugin had never compiled.** `body.TokenizedRequest`
  does not exist in `llm-d-router@v0.10.0`; the field is `TokenizedPrompt`. Every
  earlier statement about that package described code no compiler had seen.
- **F-08 — `ApplySalt` never salted `body.Generate`.** It carries `CacheSalt` and
  `tokenizer.CacheSaltFromBody` reads it, so the pre-tokenized surface routed in
  the shared namespace while the hardened profile reported itself hardened. Both
  fixed in `ec00137`, with tests that interrogate upstream rather than restate a
  list, so a dependency bump cannot silently reopen the channel.
- **F-09 — ADR-008's block was a guess.** T-003 was marked blocked on the Go
  toolchain without re-testing. Go 1.26.6 builds from source in this container,
  and the module graph resolves with a scratch-only `replace` overlay mapping
  vanity paths to GitHub (egress blocks `proxy.golang.org` and every vanity
  host). BARRIER's Go now builds, vets and tests here — which is how F-07 and
  F-08 were found. **A limit that has not been re-tested is a guess.**
- **F-10 — the design record was never committed.** `docs/design/`, `docs/tasks/`,
  `STATE.md` and the two handoff sets existed only outside the repository, while
  `README.md` pointed at an empty `docs/design/`. Restored in `aa8250b`.
- **F-11 — SGLang's determinism composes with its cache; vLLM's does not.** This
  is what made the amendment worth taking (ADR-009).
- **F-12 — SGLang takes `cache_salt`, not `extra_key`.** S-03's verdict. Same
  wire field as vLLM, salting both the radix tree and the published KV events.
  `extra_key` — the field SGLang's own docs show for multi-tenancy — namespaces
  the tree but not the event hashes, so building on it would leave llm-d's
  routing index shared (ADR-010).

### State

`make check`: ruff, ruff-format, mypy strict, **272 Python tests** — all pass.
Go: `go build ./...`, `go vet ./...` clean and **20 tests** passing on Go 1.26.6.
The `go-check` Makefile target still fails *in this container only*, because it
invokes the system Go, which tries to fetch the pinned toolchain through the
blocked proxy. On a machine with normal egress it is correct as written.

Receipt predicate is now **v0.2**. v0.1 is refused by name. No receipt had been
published, so nothing was invalidated.

### Still waiting on hardware or credentials

1. Push `provenance.bundle` to GitHub (the git proxy refuses this repo).
2. Cluster bring-up and the **S-02** spike — verdict must reach `decisions.md`
   before any oracle code. Unchanged by this amendment.
3. **T-028** GPU session, staged stage 1 → human decision → stage 2. **A-03**
   (the caching × determinism 2×2) is now an explicit stage-2 option; it is not
   scheduled, and if stage 1 shows no divergence at 0.5B it is moot.

---

## Session 2026-09-07 (later) — five GPU runs, four measured results

### What is now measured

| | result | evidence |
|---|---|---|
| Divergence exists | 34 of 128 distinct outputs at temp 0 | `bench/results/stage1-a40-2026-09-07.md`, `cost-h100-…` |
| vLLM invariance | cuts it to 5 of 128 — **reduces, does not eliminate** | `bench/results/cost-h100-2026-09-07.md` |
| vLLM cost | **22.7%** throughput, 95% CI [0.741, 0.808] | same |
| SGLang invariance | **1 of 128 — eliminates**, cache on or off | `bench/results/sglang-2x2-h100-2026-09-07.md` |
| SGLang cost, isolated | **18.0%**, cache held off both sides | same |
| Cache worth (this workload) | **−7.9%** — a penalty, not a benefit | same |

### Findings

- **F-13 — the run driver would have mislabelled half of stage 2.** It attaches
  to one engine; `batch_invariant` is read at vLLM import time. Fixed by a guard
  that refuses a cell the live engine cannot serve.
- **F-14 — that guard had the bug it was written to prevent.** It read
  `/_stub/resolved_config`, an endpoint only the test stub implements, so
  against real vLLM it returned "could not compare" and permitted the exact
  mislabelled comparison it existed to stop. An entire H100 run reported the
  opposite of the truth. It now fails closed. **Its tests passed because its
  tests used the stub that implements the endpoint.**
- **F-15 — the first "invariance fixes it" result was underpowered.** 32 trials
  could not see a residual that appears at ~4 in 128. Amended in place, not
  deleted.
- **F-16 — the confounded cost number understates rather than inflates.** 0.848×
  naive against 0.820× isolated, because the radix cache is a small penalty on a
  short shared prompt and the two effects partly cancel. The opposite of the
  intuition A-01 was written on.
- **F-17 — `token_ids` and `/server_info` were both wrong against real vLLM**
  (T-018a). Found by reading vLLM's source, before spending a GPU minute.

### Cost

Six pods, roughly **$2.00** of a $20 budget. Every failure was caught by a
number that made no sense — a 32-trial cell finishing in zero seconds, twice.

### Still open, and none of it needs rented hardware

1. **S-02 and the two-tenant topology.** Docker Desktop on `monster`; see
   `docs/RUNBOOK-local.md`. The verdict must reach `decisions.md` before any
   oracle code exists. This is the last substantial unmeasured claim.
2. **A-05** — two-engine llm-d topology in the kind chart. Backlog, needs (1).
3. Confidence intervals on the A-03 2×2; SGLang's Triton backend; dependence on
   model size and batch shape; why vLLM's 5 residual vectors remain.

---

## Finding F-18 — the topology never puts the EPP in the request path

Found 2026-09-07 by reading the deploy path against what it would actually do,
while waiting on the first CI run of `barrier.yml`. **Not yet fixed.**

`barrier/deploy/chart/templates/gateway.yaml` renders an Envoy config whose only
HTTP filter is `envoy.filters.http.router`, routing `/` straight to the `sim`
cluster. There is **no `ext_proc` filter anywhere in the chart** — the string
does not appear in `barrier/deploy/` at all. The EPP is deployed, exposes 9002,
has a Service, and is never called.

Three consequences, in descending order of seriousness:

1. **The `tenant-salt` plugin cannot run.** It is a `RequestHeaderProcessor` in
   an ext_proc server that nothing sends requests to. Every test it passes is a
   unit test.
2. **The default-vs-hardened diff would produce identical behaviour**, because
   the only rendered difference is a header-strip on a path where no component
   reads that header. `make barrier-diff` would show a real diff in YAML and no
   difference in what runs — the worst possible outcome for a deliverable whose
   whole argument is "a real gap closes with one plugin and one proxy rule".
3. **S-02 would probe a bare Envoy → simulator path**, not an llm-d routing
   layer. A `NO CLIENT-OBSERVABLE SIGNAL` verdict from that topology would be
   correct about the thing measured and meaningless about the thing claimed —
   and it is the verdict this topology is most likely to produce.

Two smaller gaps in the same file, from the same cause:

- `proxy.injectIdentityHeader: x-llmd-tenant` is declared in
  `values-hardened.yaml` and **read by no template**. The proxy strips the
  client's header and then vouches for nothing, so even with ext_proc wired the
  plugin would fail closed on every request (which is at least the safe
  direction).
- `proxy.stripInboundBodyFields: [cache_salt]` is likewise declared and
  unimplemented. Envoy cannot strip a JSON body field with the filters
  configured here; it needs a Lua filter or equivalent.

**Why this was not caught sooner.** The chart has never been applied. Every
component was reviewed in isolation and each is individually correct; the seam
between Envoy and the EPP is the one thing a unit test cannot reach. This is the
same class as the `ko` image reference (T-032) and the stub-only readback
endpoint (F-14) — a joint between two pieces, invisible until something runs.

**What it means for the claims.** Nothing published changes: no BARRIER result
has ever been asserted, and `docs/SHIP-REPORT.md` already records the attack as
*not established*. But the gap is larger than "not yet run" implied — the
topology as committed could not have demonstrated the effect even if it had been
stood up, and the ship report should say so.

**Not blind-fixed.** Wiring ext_proc correctly means an `http_filters` entry
with a gRPC service pointing at `provenance-epp:9002`, matching `processing_mode`
for request headers *and* body (the plugin rewrites `cache_salt`), plus a way to
inject a vouched identity. That is real Envoy configuration, and writing it
untested — into the one component whose failure mode is *looking like it works* —
is how F-14 happened. `barrier.yml` now gives a ten-minute loop to build it
against; the next session should use it.
