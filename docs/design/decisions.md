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

## ADR-008 — Go 1.26.6, not 1.24

**Date:** 2026-08-30 · **Phase:** 4 · **Status:** accepted · **Amends:** HLD §7.1, §7.11

**Context.** The HLD recommended Go 1.24. `llm-d-router` v0.10.0 — the pinned release
— declares `go 1.26.6` in its go.mod, so the module cannot be resolved on anything
older, and `go get` cannot auto-download a toolchain in an environment whose egress
allowlist excludes `proxy.golang.org`, `go.dev` and `dl.google.com`.

**Options.** (a) Amend to Go 1.26.6. (b) Pin an older llm-d-router that builds on 1.24.
(c) Vendor the dependency.

**Decision.** (a).

**Rationale.** (b) would have BARRIER built against a release behind the one whose
source the whole threat model was read from — F-01, F-02 and F-03 all cite v0.10.0
behaviour, and analysing one version while shipping against another is how a finding
quietly stops being true. (c) carries the fork-shaped maintenance burden ADR-002
exists to avoid.

**Consequences.** T-003 is blocked until a host with Go ≥ 1.26.6 is available; `make
go-check` self-skips with that reason rather than passing silently. T-034 and all of
M4 inherit the blocker. Any machine that builds the EPP image — Roshan's, and any CI
runner — needs the newer toolchain; the CI workflow already reads the version from
`barrier/epp/go.mod` rather than hard-coding it.
