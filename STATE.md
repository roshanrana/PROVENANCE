# STATE

Living ledger for PROVENANCE. **This file is the single source of truth for where the
project is.** Read it first in every session. Do not begin a session with a repo-wide
crawl or `git log` archaeology — this file exists so that is never necessary.

---

## Now

- **Phase:** 5 — Implementation · **everything buildable without hardware is built**
- **Status:** `make check` PASS (**250 tests, 88% coverage**) · `make attest-demo` PASS.
  ATTEST complete. BARRIER written end to end; the Go plugin's pure-crypto core is
  compiled and tested, the rest awaits its first compile.
- **Blocked on:** hardware only. Nothing further can be verified in the cloud container.
- **Next:** **Roshan runs three verifications** — see "Handoff" below.

## Handoff — three verifications, in order

Go 1.26.6 is installed on Roshan's machine (2026-08-30). The cloud container still
has 1.24.7 and cannot fetch a toolchain, so these are the steps only he can run.

**1. Compile the Go plugin** — first compile of `plugin.go`, `main.go`, `.ko.yaml`.

```bash
cd barrier/epp && GOFLAGS=-mod=mod go mod tidy && go build ./... && go test ./...
```

`salt.go` and `salt_test.go` are verified at **Go 1.26.6** — compiled, vetted,
gofmt-clean, 12 tests passing — because they use only stdlib (F-06). The whole
module is gofmt-clean at 1.26.6.

The llm-d-importing files have **never compiled**, but their interfaces were checked
against real upstream source, which caught two design errors (F-05). Remaining risk
is ordinary signature drift. Send any errors back.

**2. Bring up the cluster** — `make barrier-up PROFILE=default`. It preflights every
tool, builds the EPP image with ko, generates secrets, renders the manifests to
`bench/results/cluster-default/`, and waits for rollout. Failures are loud and the
transcript is kept.

**3. Run the S-02 spike** — port-forward, then `make barrier-spike`. Its verdict
decides BARRIER's shape and **must be recorded in `decisions.md` before any oracle
code is written**. The decision rule is carried inside the evidence file itself, so
nobody has to trust that it predated the result.

Then **T-028**, the GPU session: `make attest-stage1`, decide, `make attest-stage2`.

## F-05 — the plugin hook was wrong, and the salt field is not where I assumed *(2026-08-30)*

Found by reading upstream source after building Go 1.26.6 in the container. Both
errors would have produced a plugin that **registers successfully and is silently
inert** — a hardened run behaving exactly like the default one, which is the worst
available failure because it would have been published as a fix.

1. **`PreRequest` fires after scheduling.** Its signature takes a
   `*SchedulingResult`, so by the time it runs the prefix hash has already been
   computed and used. The correct hook is **`RequestHeaderProcessor`** — "runs
   after InferenceRequest creation but before admission control", and therefore
   before any DataProducer hashes anything.
2. **`CacheSalt` is not a field on `InferenceRequestBody`.** It lives on each
   endpoint variant (`Completions`, `ChatCompletions`, `Messages`, `Responses`,
   `Conversations`, `Embeddings`) *and* on `TokenizedRequest` — the last being what
   the prefix hasher actually reads. Setting one would close the channel for one
   API surface and leave the others open.

`ApplySalt` now stamps every populated variant and returns a count, so a test can
assert coverage rather than trust it.

## F-06 — Go 1.26.6 does build in the container *(2026-08-30)*

An earlier claim of mine was wrong. `go.dev`, `dl.google.com` and `proxy.golang.org`
are blocked, but **`github.com/golang/go` is reachable over git**, and Go bootstraps
itself:

```bash
git clone --depth 1 --branch go1.26.6 https://github.com/golang/go /tmp/goroot
cd /tmp/goroot/src && GOTOOLCHAIN=local GOROOT_BOOTSTRAP=$(go env GOROOT) ./make.bash
```

So gofmt and stdlib typechecks now run at the target version. What still cannot run
here is **module resolution**: llm-d pulls ~45 modules across ~40 vanity hosts
(`golang.org/x/*`, `k8s.io/*`, `google.golang.org/*`, `go.uber.org/*`,
`go.opentelemetry.io/*`), all blocked, and no module proxy is reachable. Mapping
them by hand to GitHub mirrors would produce a `go.mod` full of replace directives
that Roshan would have to strip out anyway.

**The first real compile is therefore still his**, but the signature-level risk it
was carrying has been retired by reading source instead.

## Known gap

The Helm chart at `barrier/deploy/chart/` is **ours, not upstream's** — the smallest
deployment that exhibits the finding. YAML parses and `up.sh` passes `bash -n`, but
neither helm nor a cluster exists in the container, so **it has never been
rendered.** Reconciling it against real llm-d behaviour is part of step 2.

---

## Gate evidence *(2026-08-30)*

| Gate | Result |
|---|---|
| `make check` | **PASS** — ruff, format, mypy (42 files), **223 tests** |
| `make attest-demo` | **PASS** |
| Coverage | **93% total**; `stats/decision` 100%, `matrix` 100%, `runid` 99%, `canonical` 98%, `divergence` 97%, `schema` 96%, `auc` 94% |

**Pre-registration is now real.** The NFR-05 thresholds (T-015) are committed at
`387aa3b`, before any attack code exists. The M5 gate checks that ordering in git
history — if it did not hold, the pre-registration would be worthless.

---

## M0 gate evidence *(2026-08-29)*

| Gate | Result |
|---|---|
| `make check` | **PASS** — ruff clean, ruff format clean, mypy clean (29 files), 124 tests |
| `make attest-demo` | **PASS** — full pipeline, stub engine, no GPU |
| Coverage (NFR-13 scope) | `common/runid` 99% · `receipt/schema` 96% · `receipt/cli` 93% · `receipt/sign` 94% · `receipt/canonical` 98% · **total 93%** |
| Flake check | `make check` run 6× consecutively, green each time |
| Go gates | **skipped, with reason** — `go-check` self-skips while `go.sum` is absent |

The walking skeleton takes one inference the whole way: matrix cell → ledger → engine →
raw JSONL → canonical receipt → ed25519 signature → verification through the shipped
CLI → manifest, in an immutable `bench/results/<run-id>/`. The demo also tampers with
the receipt and requires exit code 3 exactly — a demo that only proves the happy path
proves very little.

---

## Pending spikes

| ID | Question | Blocks | Status |
|---|---|---|---|
| S-01 | llm-d EPP plugin registration mechanism | FR-B-05 contracts | **RESOLVED** — F-02, ADR-002 |
| S-02 | Client-observable routing signal on the simulator | FR-B-03, BARRIER MVP | **open — highest priority.** Spec in LLD §7 |
| S-03 | Is the prefix index tenant-scoped? | Threat model | **RESOLVED** — F-01 |
| S-04 | Does `cache_salt` reach vLLM's engine cache? | Scope of FR-B-08 | **RESOLVED** — F-03, ADR-007 |
| S-05 | Can the proxy strip client identity headers? | FR-B-02, R-5 | **RESOLVED** — ADR-006 |

---

## F-01 — `cache_salt` already exists, and is client-supplied

`llm-d-router` seeds the prefix block-hash chain with `xxhash(TargetModel)` plus an
**optional, client-supplied** `cache_salt` (`json:"cache_salt,omitempty"`), and nothing
else. So the index is model-scoped only: two tenants on one model share a namespace.

The isolation primitive already exists — BARRIER must not claim to invent it. The real
gap is that the salt is caller-controlled and unauthenticated: an attacker omits it, an
honest tenant who forgets it is unprotected, and nothing binds a salt to an identity.

**FR-B-05 is therefore "bind the salt to authenticated tenant identity"**, not "implement
salted hashing".

## F-02 — out-of-tree plugins work; no fork needed

`plugin.Register(type, stability, FactoryFunc)` writes to an exported package-level
`Registry`, and `runner.NewRunner()…Run(ctx)` is exported — so our `main.go` can
blank-import our plugin package and run upstream's runner unmodified (ADR-002).

Shipped scheduling plugins already read request headers (`headerlabelaffinity`,
`headerprofile`, `sessionaffinity`), so tenant identity in a header reaches plugin code
at scheduling time. RSK-05 substantially de-risked.

## F-03 — `cache_salt` reaches vLLM's engine cache too

vLLM injects `cache_salt` into the first block's hash, and parent-hash chaining carries
it forward. **One derived salt can close both channels** — the EPP routing index and the
engine's real KV cache — provided the plugin rewrites the outbound request body
(LLD §4.3 obligation 3, ADR-007).

## F-04 — llm-d-router needs Go ≥ 1.26.6 *(2026-08-29)*

v0.10.0 declares `go 1.26.6`. This is a **stack-recommendation amendment**: HLD §7.1 and
§7.11 say "Go 1.24" and should read Go 1.26.6. Confirm the toolchain on any machine that
will build the EPP image — T-003, T-034 and all of M4 depend on it.

---

## Key context (so it never has to be re-derived)

- **ATTEST cannot run on the dev machine.** Batch invariance needs NVIDIA SM ≥ 8.0.
- **One GPU session, 4–6 h**, staged: ~90 min divergence hunt → decision point → ~2.5 h
  measured matrix (requirements §7.1).
- **The simulator does not vary TTFT on cache hit vs miss** (D-01). Settled.
- **Prior art:** PrefixWall (arXiv 2603.10726) and DualMap (arXiv 2602.06502). Cite both.
- **Highest project risk is RSK-01:** divergence may not appear at 0.5B. Requirements are
  written so either outcome ships.
- **Handoff docs live in `handoff/`** — `codex/` and `claude-code/`, deliberately out of
  the main tree.

---

## Current wave

**Wave 6:** T-013, T-014, T-017, T-019, T-032 — disjoint file scopes, parallelisable.
Full table: `docs/design/04-execution-plan.md`. Packs: `docs/tasks/`.

---

## Task log

| Date | ID | Task | Outcome |
|---|---|---|---|
| 2026-08-28 | — | Upstream verification | `00-upstream-findings.md`. Three brief corrections: sim TTFT gap, APC non-composition, PrefixWall prior art. |
| 2026-08-28 | — | Phase 0 intake + requirements | 15 decisions (D-01…D-15). Gate passed. |
| 2026-08-29 | — | MCP registry survey | No connector worth adding; local tooling strictly better. |
| 2026-08-29 | — | HLD + 11 stack recommendations | Gate passed. ADR-001…005. |
| 2026-08-29 | — | Spikes S-04, S-05 resolved from source | ADR-006, ADR-007. S-02 narrowed. |
| 2026-08-29 | — | LLD, contracts §4.1–4.5 frozen | Gate passed. §4.4 unfrozen pending S-02. |
| 2026-08-29 | — | Execution plan, 50 tasks / 7 milestones | **Hard gate passed.** |
| 2026-08-29 | — | Codex + Claude Code handoff packaged | `handoff/`. |
| 2026-08-29 | T-001 | Scaffold repo, uv workspace | done |
| 2026-08-29 | T-002 | Python gates: ruff, mypy strict, pytest | done. One justified suppression (N818). |
| 2026-08-29 | T-003 | Go module scaffold | **BLOCKED** — needs Go ≥ 1.26.6. See F-04. |
| 2026-08-29 | T-006 | `common/runid` | done. 99% coverage; atomic manifest writes. |
| 2026-08-29 | T-007 | `attest/harness/ledger` | done. Append-only, resume-safe, torn-line tolerant. |
| 2026-08-29 | T-008 | Stub engine | done. Flaky test found and redesigned — see pack. |
| 2026-08-29 | T-009 | Receipt schema (frozen) | done. Added `SubjectDigestMismatch` so exit 3 ≠ exit 4. |
| 2026-08-29 | T-010 | JCS canonicalisation + ed25519 | done. UTF-16 key ordering verified against a surrogate-pair case. |
| 2026-08-29 | T-011 | `attest verify` CLI | done. Every exit-code row has a test. |
| 2026-08-29 | T-004 | `make check` | done. Spans both toolchains; go-check self-skips with reason. |
| 2026-08-29 | T-005 | GitHub Actions | done. Mirrors `make check`, plus a job running the demo. |
| 2026-08-29 | T-012 | **M0 walking skeleton** | done. **Gate green.** |
| 2026-08-30 | T-013 | `common/stats/auc` — AUC + stratified bootstrap CI | done. 94%. Ties via average ranks; checked against scipy including a heavy-ties case. |
| 2026-08-30 | T-014 | `common/stats/permutation` | done. Two-sided, add-one correction so p is never reported as 0. |
| 2026-08-30 | T-015 | `common/stats/decision` — the pre-registered rule | done. 100%. Thresholds pinned by test. `attack_succeeds` and `at_chance` are deliberately not complements. |
| 2026-08-30 | T-016 | `common/stats/noise` — noise floor, trial counts | done. Reports IQR alongside SD; one outlier moves SD 100x and IQR not at all. |
| 2026-08-30 | T-017 | `attest/harness/matrix` | done. **100% coverage.** Pure function of (seed, config); cheapest-first ordering. |
| 2026-08-30 | T-022 | `attest/analysis/divergence` | done. 97%. Bitwise comparison; refuses to summarise a partial matrix. |
| 2026-08-30 | T-023 | `attest/analysis/cost` | done. Bootstrap CIs on ratios; refuses cross-hardware comparison. |
| 2026-08-30 | T-025/026 | `attest/harness/run` — staged resumable driver | done. Resume verified: completed cells re-run zero engine requests. |
| 2026-08-30 | T-018 | `attest/harness/vllm` — real engine lifecycle | done. Refuses to measure an engine whose invariance state contradicts the request. |
| 2026-08-30 | T-037 | tenant-salt derivation (Go) | done. **Compiled and tested** — 12 tests, stdlib only, so the toolchain gap did not block it. |
| 2026-08-30 | T-038/039 | Plugin wiring + outbound `cache_salt` rewrite | **written, never compiled.** Needs step 1. |
| 2026-08-30 | T-034 | Custom EPP `main.go` + ko | **written, never compiled.** |
| 2026-08-30 | T-032/033 | kind bring-up + Helm chart | **written, never rendered.** See Known gap. |
| 2026-08-30 | T-040/041 | `values-default` vs `values-hardened` | done. Three changes; `make barrier-diff` shows them. |
| 2026-08-30 | T-035 | S-02 spike script | done. Discriminator logic tested (10 tests); the run needs a cluster. |
| 2026-08-30 | T-036 | `docs/threat-model.md` | done. Three failure modes, two channels, explicit non-defences. |
| 2026-08-30 | T-047 | README | done. No placeholder numbers — none exist yet. |

---

## Blockers

- **All remaining work needs hardware.** Nothing further can be verified in the cloud
  container: no Go 1.26.6, no helm, no cluster, no GPU.
- **T-003** — `go mod tidy` on Roshan's machine. Handoff step 1.

---

## Deviations from plan

| Date | Deviation | Why |
|---|---|---|
| 2026-08-29 | `pyproject.toml` written once with T-001 + T-002 content | Same file; creating it bare and immediately rewriting is waste. |
| 2026-08-29 | `attest/receipt/provenance.py` (T-019) landed early | `attest verify --online` (T-011/T-020) cannot resolve its import without it, and exits 5/6 would have been untestable. ~90 lines, tested. T-019 now covers offline fixtures and the harness integration only. |
| 2026-08-29 | `attest/harness/engine.py` (part of T-018) landed early | M0 must exercise the engine interface end to end. Real vLLM process lifecycle — launch, env, readiness, teardown — remains T-018. |
| 2026-08-29 | `SubjectDigestMismatch` added to the frozen LLD §4.1 module | Additive: a new exception type, no field or contract change. Required to honour the §5 exit-code taxonomy. |
| 2026-08-29 | HLD says Go 1.24; actual requirement is Go 1.26.6 | Upstream. See F-04. Amend HLD §7.1 and §7.11 at the next gate. |
