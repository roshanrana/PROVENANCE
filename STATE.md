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

---

## Finding F-19 — `barrier/epp/go.sum` was never generated by a real `go mod tidy`

Found 2026-09-07 from BARRIER CI run #3, which got past the exec-bit failure and
died in `ko build` with ten `missing go.sum entry` errors — grpc, protobuf,
go-control-plane's ext_proc types, and more.

`go.sum` has **56 lines and zero entries** for `google.golang.org/grpc` or
`google.golang.org/protobuf`. A complete sum file for this graph is hundreds.

**Cause, and it is mine.** This container cannot reach `proxy.golang.org` or any
vanity host, so `go mod tidy` has never completed here. Everything I verified
about the Go module — build, vet, 22 tests — was verified through the scratch
`replace` overlay described in ADR-008, which maps each vanity path to its GitHub
repository. That overlay is deliberately never committed, because a reader who
cloned it would inherit an unbuildable module.

The flip side went unnoticed: **the committed `go.mod`/`go.sum` pair was never
produced by a real resolution**, and nothing built the module from the committed
state on a normal network until CI did. Every green Go gate in this session ran
against the overlay, not against what is in the repository.

That is the same shape as F-14 — a check that passed because it was run against
the thing that accommodates it rather than the thing that would refuse it.

**Fix.** One `go mod tidy` on a machine with open egress. Not something CI should
paper over: if `go.sum` is incomplete, the build *should* fail, and a workflow
step that silently tidied would hide the defect rather than surface it.

**What it does not affect.** No published claim. The plugin's behaviour was
verified against the real `llm-d-router@v0.10.0` source — the overlay changes
where modules are fetched from, not what they contain. The defect is in the
repository's ability to build itself from a clean clone, which is exactly what a
reviewer would try first.

---

## Finding F-20 — `ko`'s `kind.local` publisher cannot tag on a multi-node kind cluster

Found 2026-09-07 from BARRIER CI run #4 (`fc3c08c`), which got past F-19 — the
module resolved, the EPP compiled, the image built and loaded — and then died at
2m40s into the bring-up step:

```
Loaded kind.local:a861e236…
Adding tag dev
Error: failed to publish images: … failed to tag image: command
  "docker exec --privileged provenance-worker ctr --namespace=k8s.io images tag --force
   kind.local:a861e236… kind.local:dev" failed with error: exit status 1
ctr: image "kind.local:a861e236…": not found
```

`ko` with `KO_DOCKER_REPO=kind.local` loads the image and then runs `ctr images
tag` on **every** node. `kind-config.yaml` asks for control-plane + two workers
(deliberately — see the comment there), and the tag step ran on
`provenance-worker` before, or without, the load reaching that node.

**Fix.** Build into the local Docker daemon (`ko.local`) and distribute with
`kind load docker-image`, which is kind's own path and handles every node. The
tag is now unique per run — `epp-<short-sha>-<epoch>` — rather than a fixed
`dev`: a mutable tag on a side-loaded image is precisely the ADR-008 hazard of a
hardened deploy silently running a stale default binary, and
`imagePullPolicy: IfNotPresent` cannot resolve a tag nothing else produced.

`up.sh` no longer predicts the image name from the flags either. `ko` prints a
*digest* reference on stdout, which `kind load docker-image` will not take, and
its repository naming varies with `--bare` / `--preserve-import-paths` / the
`ko.local` defaults. The script asks the daemon for the image carrying its own
unique tag, and refuses — printing what the daemon does hold — if it is absent.

**What it does not affect.** No published claim. This is the third defect in the
deploy path found by running it rather than reading it (F-18, F-19, F-20), and
none of the three could have been caught by `make check`.

**Still behind it: F-18.** The chart puts no `ext_proc` filter in front of the
simulator, so even a clean bring-up deploys an EPP that is never in the request
path, and `default` and `hardened` would produce identical results. Run #5 going
green is a bring-up result, not a spike result.

---

## Finding F-21 — the scheduling profile named a plugin that does not exist

Found 2026-09-07 while wiring F-18, by reading llm-d's own shipped EPP configs
(`config/charts/routerlib/templates/_config.yaml`, `deploy/config/dp-epp-config.yaml`)
rather than by running anything. Three defects in the one file CLAUDE.md calls
"the file the whole result turns on":

1. **No `apiVersion` / `kind`.** The runner decodes this as a typed
   `EndpointPickerConfig`; a bare mapping is rejected. The EPP would have
   crash-looped before serving a request. The group is `llm-d.ai/v1alpha1` —
   `inference.networking.x-k8s.io` was deprecated upstream in PR #972.

2. **`least-queue-filter` does not exist.** Zero matches in llm-d-router at any
   ref. It was invented, and it sat in both profiles as a `pluginRef`.

3. **Nothing was declared.** `plugins:` DECLARES, `schedulingProfiles:`
   composes. `values-default.yaml` had no `plugins:` block at all, so every
   `pluginRef` in it was dangling. And `values-hardened.yaml` listed
   `tenant-salt` as a scheduling `pluginRef` — but `TenantSalt` implements
   `requestcontrol.RequestHeaderProcessor`, not a scheduling interface, so it is
   activated by *declaration* and would have been rejected in a profile.

**Fix.** Both profiles now declare `prefix-cache-scorer` and `queue-scorer` and
compose them identically; hardened additionally declares `tenant-salt` outside
the profile. The profiles being byte-identical is deliberate: the mitigation must
change which namespace the hashes fall in, not how endpoints are scored, or the
diff between the two runs stops being the mitigation.

The unwired `routing.prefixCacheScorer.blockSize` / `maxPrefixBlocks` knobs are
gone. No template ever read them, and configuration that looks live but is inert
is the same class of defect as F-18.

**What it does not affect.** No published claim. But note the shape: F-18, F-19,
F-20 and F-21 are all in the deploy path, all invisible to `make check`, and
three of the four were found by reading or running the thing rather than by any
test this repository owns. That is the honest summary of BARRIER's maturity.

---

## Finding F-22 — the simulator's latency flags are Go durations, not integers

Found 2026-09-07 from BARRIER CI run #5 (`8d66105`), which is the first run that
got the topology *up*:

```
provenance-epp-…       1/1  Running
provenance-gateway-…   1/1  Running
provenance-sim-…       0/1  CrashLoopBackOff  (×2)

failed to read configuration err="invalid argument \"200\" for
  \"--time-to-first-token\" flag: time: missing unit in duration \"200\""
```

`llm-d-inference-sim` documents it plainly — *"All latency-related parameters are
defined in duration format, e.g. 100ms. Integer format is deprecated."* — and
`:latest` has since removed the integer form outright. `200ms` / `10ms`.

**The image is now pinned to `v0.11.2`.** `:latest` is how this arrived: the
values file was written against a simulator that accepted integers and silently
stopped being that simulator. A topology whose output is evidence cannot depend
on an image that changes underneath it, and this repository's whole subject is
claims a reader can re-derive.

### What run #5 confirmed, which matters more than what it broke

F-18, F-20 and F-21 are **fixed, by evidence rather than by argument**:

- `ko build` → `kind load docker-image` distributed the image to all three
  nodes. F-20 closed.
- The EPP parsed its config and reached Ready: `gRPC server listening name=ext-proc
  port=9002`, `name=health port=9003`, pod controller started, caches populated.
  That is the `apiVersion`/`kind` envelope, the declared plugins and the
  standalone `--endpoint-selector` discovery all working. F-21 closed.
- Envoy accepted the `ext_proc` filter and the `ORIGINAL_DST` cluster —
  `cm init: all clusters initialized`, `starting main dispatch loop`, gateway
  1/1 Running. The EPP is in the request path for the first time. F-18 closed
  as far as the *wiring* goes.

**Still open from F-18:** `proxy.injectIdentityHeader` and
`proxy.stripInboundBodyFields` are declared in `values-hardened.yaml` and read by
no template. Until they are, the hardened profile reads a client-controlled
identity header, and the mitigation is forgeable at the edge. `stripInboundHeaders`
is wired; the injection half is not.

---

## Finding F-23 — S-02 returned ORACLE VIABLE on a millisecond counter

Found 2026-09-07 from BARRIER CI run #6 (`86dbc86`) — the first green run, and
the first time the spike executed at all. Full writeup:
`bench/results/s02-run6-2026-09-07.md`, kept including the wrong verdict.

The single discriminator it found was `x-envoy-upstream-service-time`: Envoy's
per-request upstream latency in milliseconds, which differs between any two
probes whatever the cache state. The refutation was three lines above it in the
same output — hit median 214.8 ms against miss median 214.5 ms, on a simulator
that by construction does not vary TTFT on cache hit versus miss (D-01).

**Cause.** `find_discriminators` implemented "fields that differ" behind a
five-name ignore-list, while its docstring promised "fields that differ for
reasons related to routing". An ignore-list only excludes the noise you already
named. Replaced with a property test: a field counts only if it differs in
*every* pair (consistent) and does not take a fresh value on every probe on both
sides (classifying). Rejected candidates are now published with their reason.

**This is a defect fix, not a change to the decision rule.** LLD §7 is untouched.

**Second time this shape has appeared**, after ship-report defect #6. Both times
the refuting evidence was already in the output and nothing external was needed.

**S-02's verdict is still unrecorded.** It does not reach `decisions.md`, and no
oracle code is written, until a run under the corrected rule returns one.

### What run #6 did establish

The topology works end to end: EPP 1/1 with ext-proc on 9002, gateway 1/1 with
all Envoy clusters initialized, both simulators Ready, 24 probes answered. F-18,
F-20, F-21 and F-22 are closed by a run rather than by an argument.

---

## Finding F-24 — the fix for F-23 did not fire, for a subtler reason

Run #7 (`677dee4`) returned `ORACLE VIABLE` on
`x-envoy-upstream-service-time` again, with no rejection printed: the corrected
rule never triggered.

F-23's fix rejected a field whose values were *all distinct* on both sides.
Millisecond integers collide by chance over eleven probes, so that test was
simply false. The fix was looking for a pattern in the values when what
disqualifies the field is the **type** of the values.

**Correction.** The spike now separates two kinds of evidence:

- **Categorical** (non-numeric): must differ in every pair, and no value may
  appear on both sides.
- **Continuous** (latency, and every numeric header): judged by
  `common.stats.decision.decide` — the pre-registered AUC / bootstrap CI /
  permutation rule from NFR-05, scored in both orientations, keeping the
  attacker-favourable one.

The timing question is now *answered* rather than narrated. `--repeats` in CI
goes 10 → 30.

**Thresholds unchanged**, and `tests/common/test_decision_thresholds.py` still
guards them. The full argument for why this is a correction rather than tuning —
and the three things a reader should check to hold us to that — is in
`bench/results/s02-run6-2026-09-07.md`, along with both wrong runs.

**S-02's verdict remains unrecorded.** Nothing reaches `decisions.md` until a run
under the corrected rule returns one.

---

## Finding F-25 — the ground-truth gate failed for a reason that had nothing to do with ground truth

Run #9 (`079cbfd`) went through the topology, the port-forward and the spike,
then died in the new **Capture the EPP's ground truth** step with `exit code 22`
after thirty identical `Handling connection for 9090` lines.

Exit 22 is `curl -f` refusing an HTTP error status. The EPP requires a bearer
token on `/metrics` by default, so the endpoint was answering `401` the whole
time — healthy, reachable, and rejected by the readiness loop as if it were
down. The step then reported nothing about the EPP at all.

Two fixes, and the second matters more than the first:

1. `--metrics-endpoint-auth=false` on the EPP. Its metrics are the *only* ground
   truth for whether the prefix index ever recorded a match. Off here because
   this is a single-tenant kind cluster with no ingress to that port; upstream's
   own chart gates the flag the same way.
2. **The gate now says what it saw.** Any HTTP status counts as "up"; the status
   code is echoed; and on failure it prints the response head and the list of
   metric families present. A gate whose failure message is silence cannot
   distinguish the thing it was built to distinguish — which is precisely the
   defect it exists to catch, reproduced in the guard itself.

That last shape has now appeared twice: ship-report defect #6 was a guard
containing the bug it was written to prevent. Worth naming as a pattern rather
than as two coincidences.

**S-02's verdict remains unrecorded.**

---

## Finding F-26 — the ground-truth gate passed on evidence that proved nothing

Run #10 (`8592807`) went green: the metrics endpoint answered `200`, the gate
found "prefix" in the dump and let the verdict stand. What it actually found
was:

```
inference_extension_plugin_duration_seconds_bucket{
    plugin_name="approx-prefix-cache-producer", ...} 64
```

That is a *timing histogram for a plugin whose name contains "prefix"*. It
proves the producer executed on all 64 probes. It says **nothing** about whether
the index ever matched a prefix — which is the only fact the control needs, and
the entire reason the gate was added one run earlier.

So the gate reproduced, in itself, the defect it exists to catch: it could not
distinguish "no client-observable signal" from "the router never indexed a
prefix". Third instance of that shape (ship-report defect #6, F-25, now this).

**Fix.** The assertion moves out of a `grep` in the workflow and into
`barrier/attack/ground_truth.py`, with eight tests — including one built from
the exact metric line that fooled the grep. It reads the
`prefix_indexer_hit_ratio` histogram (either published family, so an upstream
rename cannot silently disarm it), subtracts the `le="0"` bucket from the
observation count, and requires the remainder to be positive:

    lookups > 0  and  lookups − matched-nothing > 0

A gate written as an untested shell one-liner is a gate nobody has checked. This
one fails the build if its own logic breaks.

**S-02's verdict remains unrecorded.** Run #11 is the first that can earn it.
