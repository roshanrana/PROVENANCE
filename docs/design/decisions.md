# Decision Log

Append-only. Mini-ADRs: context, options, decision, rationale, consequences.
Intake decisions D-01 … D-15 live in `01-requirements.md` §2 and are not repeated here.
This log starts at Phase 1 and records decisions made *during* design and build.

---

## ADR-001 — Monorepo of CLIs, no services

**Date:** 2026-08-29 · **Phase:** 1 · **Status:** accepted

**Context.** PROVENANCE must let a stranger reproduce results with no accounts (P-02, D-13)
and must trace every published number to committed evidence (NFR-01). Work is split across
three environments that cannot see each other's filesystems (§6.4).

**Options.** (a) Monorepo of independent CLIs over files. (b) A results service with a
database and dashboard. (c) One unified CLI spanning both workstreams.

**Decision.** (a).

**Rationale.** Files under git are the simplest traceability story available; a database
puts published numbers behind something that can drift. Self-contained CLIs are also the
only shape that composes across the three-environment split. (c) would couple two
workstreams that must ship independently (D-04).

**Consequences.** No runtime to maintain. Analysis must never mutate raw output
(single-writer per `run-id`). A dashboard, if ever built, is a mirror and never a source of
truth.

---

## ADR-002 — Out-of-tree Go module rather than a fork

**Date:** 2026-08-29 · **Phase:** 1 · **Status:** accepted · **Resolves:** S-01, most of A-05

**Context.** FR-B-05 requires a real, registered llm-d EPP plugin. It was unknown whether
the framework supports out-of-tree plugins.

**Options.** (a) Out-of-tree module importing upstream's runner. (b) Fork llm-d-router.
(c) Configuration-only mitigation with no custom code.

**Decision.** (a).

**Rationale.** Confirmed from source: `plugin.Register(type, stability, FactoryFunc)` writes
to an exported package-level `Registry`, and `runner.NewRunner()…Run(ctx)` is exported. So
our `main.go` can blank-import our plugin package — whose `init()` registers it — and then
run upstream's runner unmodified. A fork carries permanent merge burden and reviewers
discount forked demos. (c) cannot express identity binding, so the mitigation would not
exist.

**Consequences.** We track the runner API across releases and pin the module version.
The deliverable becomes "a plugin you can drop into your own EPP build," which is a
stronger artifact than a fork. Upgrades are a `go.mod` bump plus a compile check.

---

## ADR-003 — Own the statistical test rather than import it

**Date:** 2026-08-29 · **Phase:** 1 · **Status:** accepted

**Context.** NFR-05 pre-registers AUC with bootstrap CI and a permutation test as the bar
for both BARRIER's attack and its mitigation. The test is a headline claim of the project.

**Options.** (a) numpy + scipy with AUC, bootstrap and permutation implemented in
`common/stats`. (b) scikit-learn's `roc_auc_score`. (c) statsmodels.

**Decision.** (a), unit-tested against scipy reference values.

**Rationale.** A reviewer assessing whether the security claim holds should be able to read
the test in about forty lines rather than trust a library call. This is one of the few
places where writing it ourselves is the *more* credible choice. It also keeps the
dependency surface small for NFR-08.

**Consequences.** NFR-13's 80% coverage bar applies here hardest. Both the attack test and
the mitigation test must use this one implementation — two implementations would make the
comparison meaningless — so its API freezes at Phase 2 as the repo's only cross-workstream
contract.

---

## ADR-004 — Helm with two values files as the mitigation's presentation

**Date:** 2026-08-29 · **Phase:** 1 · **Status:** accepted

**Context.** BARRIER must show a reader exactly what changes between the leaking and the
hardened deployment (FR-B-02, FR-B-05, NFR-18).

**Options.** (a) Helm with `values-default.yaml` and `values-hardened.yaml`.
(b) Kustomize overlays. (c) Raw YAML per configuration.

**Decision.** (a).

**Rationale.** The *diff between the two values files is the deliverable* — it is the
artifact that makes "configuration and threat-model gap" (NFR-18) concrete rather than
asserted. Helm also matches how llm-d is actually deployed, so the files read as something
a customer would recognise. Kustomize is more transparent but diverges from upstream's
distribution path.

**Consequences.** Templating opacity when debugging. Mitigated by keeping our values thin
over upstream charts and by committing the rendered output alongside results.

---

## ADR-005 — ed25519 with in-toto predicate; sigstore deferred

**Date:** 2026-08-29 · **Phase:** 1 · **Status:** accepted

**Context.** FR-A-06 requires receipt verification that works offline, with no network and
no running engine, and D-13 bars account requirements from the reproduction path.

**Options.** (a) ed25519 via `cryptography`, in-toto style predicate. (b) Sigstore keyless
via cosign. (c) GPG.

**Decision.** (a), with sigstore documented as future work.

**Rationale.** Keyless signing is the stronger provenance story but requires network and
OIDC at verify time, which directly contradicts FR-A-06 and D-13. The in-toto predicate
shape gives most of sigstore's legibility to a security reviewer at none of its
infrastructure cost.

**Consequences.** We own key custody (§8.2 of the HLD). CI signs fixtures with a fixed,
clearly-labelled test key, and the tooling must refuse to sign a non-test receipt with it —
that refusal needs a test.

---

## ADR-006 — Strip the identity header at the proxy, and fail closed in the plugin

**Date:** 2026-08-29 · **Phase:** 2 · **Status:** accepted · **Resolves:** S-05

**Context.** FR-B-05's mitigation derives a cache salt from a tenant identity header. If a
client can set that header itself, the mitigation is forgeable at the edge and the result
collapses (HLD R-5).

**Options.** (a) Strip at the proxy via Envoy config in the Helm values. (b) Add our header
to llm-d's `InputControlHeaders` set upstream. (c) Trust the header as received.

**Decision.** (a), plus `failClosed: true` in the plugin.

**Rationale.** llm-d already implements this defence for its own control headers —
`InputControlHeaders` and `OutputInjectionHeaders`, enforced via `IsSystemOwnedHeader()` at
`handlers/request.go:142` and `handlers/response.go:202` — but those sets are hardcoded
package-level vars, so (b) needs an upstream change we do not want to depend on. Stripping
at the proxy puts the defence at the trust boundary where authentication already happens.
Fail-closed means the plugin never silently routes with an empty salt if stripping is
misconfigured.

**Consequences.** The stripping config is part of the deliverable and must exist before the
attack runs (FR-B-02). The threat model must state that the proxy is the trust boundary and
that the plugin's guarantee is conditional on it. Contributing the header upstream becomes
possible follow-on work.

---

## ADR-007 — The salt must be propagated to the engine, not only the EPP index

**Date:** 2026-08-29 · **Phase:** 2 · **Status:** accepted · **Resolves:** S-04

**Context.** The HLD assumed the mitigation closed the EPP's routing index and left the
precise path (the engine's real KV cache) as an open residual to be characterised.

**Options.** (a) Derive the salt and use it only for the EPP hash chain. (b) Additionally
rewrite the outbound request body's `cache_salt` so the engine partitions identically.

**Decision.** (b).

**Rationale.** vLLM's prefix-caching design confirms `cache_salt` is shipped and enters the
engine's own block hash — injected into the first block's hash, and carried forward by
parent-hash chaining. So one derived salt can close both channels. Doing only (a) would
close the routing index while leaving the engine cache shared across tenants, which is the
weaker half of the mitigation presented as the whole.

**Consequences.** FR-B-05 gains a third contractual obligation (LLD §4.3), and FR-B-08's
residual shrinks from "a second open channel" to "whatever survives partitioning both."
The plugin must be able to mutate the outbound request body, which constrains where in the
request lifecycle it hooks — to be confirmed against the runner API during implementation.

---

## ADR-008 — The Go toolchain block is retired, not designed around

**Date:** 2026-09-07 · **Phase:** 5 · **Status:** accepted · **Supersedes:** the BLOCKED note in `docs/tasks/T-003-go-scaffold.md`

**Context.** `llm-d-router@v0.10.0` declares `go 1.26.6`. The build container shipped
1.24.7, and T-003 was marked blocked under the two-strike rule, with an earlier amendment
to HLD §7.1 accepting that BARRIER's Go would not compile in an agent-reachable
environment.

**Options.** (a) Keep the block and defer every Go compile to the user's machine.
(b) Build Go 1.26.6 from source in the container. (c) Downgrade the router dependency.

**Decision.** (b), plus a scratch-only `replace` overlay for module resolution.

**Rationale.** The block was asserted rather than tested. Re-testing found
`github.com/golang/go` reachable over git, and `GOTOOLCHAIN=local
GOROOT_BOOTSTRAP=$(go env GOROOT) ./make.bash` produced a working 1.26.6. Module
resolution then failed separately, because egress blocks `proxy.golang.org` and every
vanity host; mapping each vanity path to its GitHub repository in a **scratch copy** of
the module resolves the graph. (c) was never viable — the frozen contracts are written
against v0.10.0's interfaces.

**Consequences.** BARRIER's Go now builds, vets and tests in the container, which is how
the two defects in ADR-010 were found. The `replace` overlay is never committed: it is a
container workaround, and a reader who cloned it would inherit an unbuildable module. On
a machine with normal egress, plain `go mod tidy` is correct and no overlay is needed.
The general lesson is recorded because it cost real time: **a limit that has not been
re-tested is a guess.**

---

## ADR-009 — SGLang as ATTEST's control arm for the cost-of-determinism decomposition

**Date:** 2026-09-07 · **Phase:** 5 (plan amendment A-01) · **Status:** accepted

**Context.** ATTEST's headline deliverable is the cost of determinism. vLLM's
batch-invariant kernels are not integrated with prefix caching upstream, so D-06 pins APC
off for the primary claim. Every cost number ATTEST can produce on vLLM alone therefore
measures *determinism plus the loss of the prefix cache*, with no way to separate the two.

**Options.** (a) Publish the vLLM number with a stated caveat. (b) Add SGLang as a second
engine and decompose. (c) Drop the cost claim.

**Decision.** (b), narrowly: harness and spike now, measurement held behind T-028's
existing human decision point.

**Rationale.** SGLang runs deterministically **with** the radix cache on
(`--enable-deterministic-inference` on the FA3 or Triton attention backend; FlashInfer
cannot). That supplies the missing cell of the caching × determinism 2×2: `C − D` isolates
what the cache is worth under determinism, `D − B` isolates determinism's own cost. On
vLLM alone only the sum is observable, and it would be published under the wrong name.
(a) leaves the obvious reviewer question — *isn't this really the prefix-cache loss?* —
with no answer. (c) discards the project's most distinctive result.

The second engine is admitted as **methodology, not coverage**, and the write-up must
lead with the decomposition. "Also supports SGLang" is a weaker line than one deep result,
and framing it that way would make the amendment a net loss.

**Consequences.** D-06 is amended: prefix caching is pinned off *for vLLM*, and the reason
is an upstream integration gap rather than a property of determinism. `EngineState` gains
an engine discriminator while the receipt schema stays versioned and stable. No GPU minute
is committed by this ADR. The negative-result rule applies unchanged: if SGLang's
deterministic mode shows no measurable advantage, that is the published result. Any
measurement must pin the SGLang version and endpoint, because
`sgl-project/sglang#15481` reports seeded determinism misbehaving on `/v1/completions`.

---

## ADR-010 — BARRIER's mitigation is engine-portable, and the portability is asserted by test

**Date:** 2026-09-07 · **Phase:** 5 · **Status:** accepted · **Resolves:** S-03

**Context.** A-01 raised the possibility that obligation 3 (partition the engine's own KV
cache) could not be met on SGLang, which would have made the mitigation engine-scoped and
forced a published limitation.

**Options.** (a) Publish the mitigation as vLLM-only. (b) Extend it to whatever field
SGLang uses. (c) Establish that no change is needed.

**Decision.** (c), on the evidence in `docs/design/spikes/S-03-sglang-cache-salt.md`.

**Rationale.** SGLang accepts `cache_salt` — llm-d's own field name — on `/generate`,
`/v1/completions`, `/v1/chat/completions` and responses, and it namespaces both the
in-process radix tree and the KV-event hashes SGLang publishes, seeded with an explicit
`sglang-cache-salt-v1\0` domain separator. The salt reaches an SGLang engine by exactly the
path it reaches a vLLM one.

Two findings from the spike change what the project says rather than what it builds.
**`extra_key` is the wrong field**: it namespaces the in-process tree but is not folded
into the published event hash, so a mitigation built on it would close the engine cache
and leave the routing-derived index shared — and `extra_key` is the field SGLang's own
prefix-caching documentation shows for multi-tenancy. And **the unsalted path is the
shared namespace on SGLang too**, which makes BARRIER's unenforced-control thesis a
cross-engine pattern rather than a single-implementation quirk.

**Consequences.** A-04 shrinks from "extend the mitigation" to a test plus a threat-model
paragraph. The claim must be stated as *verified by source read at commit `30705c0`*, not
as measured, until A-03 runs against a live engine — and it must pin a version, since
llm-d's SGLang manifest targets `lmsysorg/sglang:v0.5.12`, which this spike did not check.

---

## ADR-011 — S-02: no client-observable routing oracle on the simulator; FR-B-03 rescopes

**Date:** 2026-09-07 · **Phase:** 5 · **Status:** accepted · **Resolves:** S-02
**Evidence:** BARRIER CI run #12, SHA `3c966e2`, `bench/results/s02-run6-2026-09-07.md`

**Context.** BARRIER's attack rests on a premise nobody had tested: can an ordinary API
caller observe anything that distinguishes a routing cache hit from a miss? LLD §7 fixed
the consequence of both answers in advance, before any evidence existed.

**Decision.** **No.** FR-B-03 rescopes to an operator-instrumented demonstration; the
attacker-observable oracle moves entirely to FR-B-09 on real vLLM.

**The measurement**, 404 probes against the two-tenant kind topology, judged by the
pre-registered rule in `common/stats/decision.py` (NFR-05: AUC ≥ 0.75, CI lower bound
above chance, p < 0.01 — all three, thresholds untouched since before any attack code):

| channel | AUC | 95% CI | p | n | clears bar |
|---|---|---|---|---|---|
| latency | 0.5581 | [0.5026, 0.6138] | 0.0425 | 402 | **no** |
| `x-envoy-upstream-service-time` | 0.5537 | [0.4984, 0.6090] | 0.0613 | 402 | **no** |

No categorical discriminator was found in any response header or body shape.

**Ground truth**, without which the negative means nothing: the EPP's prefix index was
consulted 404 times and **matched a non-zero prefix on 402 of them**, mean match ratio
0.990, index size 8. The router had something to leak. This is a result about
observability, not about a cluster where nothing was cached.

**Say it precisely: this is "no oracle", not "no effect".** The latency interval's lower
bound is 0.5026 — above chance — with p = 0.0425. Under the pre-registered rule the result
is *neither* `attack_succeeds` nor `at_chance`, which is the middle case
`common/stats/decision.py` was deliberately written to be able to express. A real but tiny
timing difference exists and is nowhere near strong enough to classify single requests.
And it almost certainly is not a *cache* signal: the simulator does not vary TTFT on cache
hit versus miss at all (D-01), so what is being measured is queueing across the two
simulator pods that prefix affinity concentrates load on.

**Rationale for accepting rather than re-running.** n=402 was fixed in the workflow before
this run, precisely so the answer could not be reached by stopping when it looked
convenient. Two earlier runs at n=62 left the interval straddling chance; this one resolves
it. Running further would be optional stopping.

**Consequences.**
- FR-B-03 is an instrumented demonstration: the leak is shown from the EPP's own index,
  which is a claim about a *routing* channel and is what the mitigation actually closes.
- The attacker-observable oracle is FR-B-09's problem, on real vLLM, where TTFT does vary
  with cache state. Nothing in this ADR says the oracle is impossible there — it says the
  simulator cannot answer the question, which is what D-01 predicted.
- Oracle code may now be written. It could not be before this line existed.
- The result is publishable as it stands and NFR-17 anticipated it.

---

## ADR-012 — FR-B-03 measured: the routing-index leak exists and the tenant salt closes it

**Date:** 2026-09-07 · **Phase:** 5 · **Status:** accepted
**Evidence:** BARRIER CI run #15, SHA `a357e08`,
`bench/results/frb03-run15-2026-09-07.md`

**Context.** BARRIER has claimed since its requirements that llm-d's prefix-cache
routing shares a namespace across tenants, and that a salt derived from
authenticated identity closes it. Neither half had ever been measured.

**Decision.** Both are now measured, on the same schedule, by the rule fixed in
advance (NFR-05):

| profile | probe | control | AUC | 95% CI | p | verdict |
|---|---|---|---|---|---|---|
| default | 1.0000 | 0.0000 | 1.0000 | [1.0000, 1.0000] | 9.999e-05 | `attack_succeeds` |
| hardened | 0.0000 | 0.0000 | 0.5000 | [0.5000, 0.5000] | 1 | `at_chance` |

**Rationale for believing the hardened zero.** The same job's ground-truth step
shows the index matching 401 of 404 lookups on that cluster. The index works
under `hardened`; what goes to zero is specifically one tenant reaching
another's entry.

**Scope, stated so it cannot be quoted past.** This is a **confirmation** oracle,
not an extraction one: the probe sends the victim's text verbatim, so a match of
1.0 is by construction. It establishes that an attacker who can *guess* a prefix
gets it confirmed by the routing layer — which matters where prompts are
predictable — and establishes nothing about recovering unknown content. The
degenerate intervals reflect zero variance in the observations, and `p` sits at
the permutation floor.

**Consequences.**
- FR-B-03 is satisfied in the form ADR-011 rescoped it to: operator-instrumented,
  read from the router's own index.
- The two-profile diff (`values-default.yaml` against `values-hardened.yaml`) is
  now backed by a measurement rather than by an argument.
- The partially-shared-prefix workload, where the ratio becomes continuous rather
  than binary, is the obvious follow-up and is not done.
