# T-003 — Go module scaffold and lint for `barrier/epp`

**Status:** blocked · **Milestone:** M0 · **Wave:** 2 · **Depends on:** T-001 · **Env:** cloud container

## Goal

A Go module at `barrier/epp` that depends on a **pinned** `llm-d-router` version, compiles,
and passes `gofmt` and `golangci-lint`. No plugin logic and no `main.go` wiring yet — this
task proves the dependency resolves and the toolchain works.

## Context

- ADR-002: we build an **out-of-tree module**, never a fork. Confirmed from source —
  `plugin.Register` and `plugin.Registry` are exported, and `runner.NewRunner()…Run(ctx)`
  is exported, so our own `main.go` can register a plugin and run upstream's runner.
- R-4 (HLD §10): upstream API drift is the standing risk. Pinning the module version and
  compiling against the pin in `make check` is the mitigation — so the pin matters here.
- Go 1.24 (HLD §7.1). Image build is **ko** (HLD §7.6), configured in T-034, not here.
- This is the only Go in the repo. Keep the boundary at the process edge: no cgo, no
  bindings, no shared build with Python.

## Contracts to honor

Module path: `github.com/<owner>/provenance/barrier/epp` (owner from the eventual GitHub
repo; a placeholder is acceptable and is corrected in T-034).

Pin `github.com/llm-d/llm-d-router` to an **exact released version**, not `latest` and not a
pseudo-version off `main` (NFR-02). Record the chosen version in the handoff notes — later
packs reference it.

Plugin type string, for when logic arrives: `tenant-salt` (LLD §4.3).

## File scope

**Create:**
- `barrier/epp/go.mod`, `barrier/epp/go.sum`
- `barrier/epp/.golangci.yml`
- `barrier/epp/doc.go` (package doc; keeps the module non-empty and compilable)

**Modify:** none.

Exhaustive. Do not create `cmd/epp/main.go` or anything under `plugin/` — those are T-034
and T-037.

## Suggested steps

1. `go mod init` at `barrier/epp`.
2. Add `github.com/llm-d/llm-d-router` at a specific released tag; run `go mod tidy`.
3. Write `doc.go` with a package comment stating the module's purpose and citing ADR-002.
4. Configure `.golangci.yml`: enable `govet`, `staticcheck`, `errcheck`, `ineffassign`,
   `revive`, `gosec`. `gosec` matters — this module handles an HMAC secret (LLD §4.3).
5. Confirm `go build ./...`, `gofmt -l .` (empty output), and `golangci-lint run` all pass.

## Acceptance criteria

- [ ] `go build ./...` succeeds inside `barrier/epp`
- [ ] `go.mod` pins `llm-d-router` to an exact released version — no `latest`, no pseudo-version
- [ ] `go.sum` is committed
- [ ] `gofmt -l .` produces no output
- [ ] `golangci-lint run` passes with `gosec` enabled
- [ ] The upstream `plugin` and `runner` packages are importable — prove it with a compiling
      reference in `doc.go` or a scratch file you then delete
- [ ] Pinned version recorded in the handoff notes

## Validation

```bash
cd barrier/epp
go build ./... && go vet ./...
gofmt -l . | tee /dev/stderr | wc -l   # must be 0
golangci-lint run
```

## Out of scope

`main.go` and runner wiring (T-034). ko configuration (T-034). Any plugin implementation
(T-037, T-038, T-039). Anything touching Python or the `Makefile` (T-004).

## Handoff notes

**Status: BLOCKED** (2026-08-29) — environment, not design.

`llm-d-router` v0.10.0 (latest release) declares `go 1.26.6`. The build environment
has Go 1.24.7, and no toolchain source is reachable from it — `proxy.golang.org`,
`go.dev`, `dl.google.com` and `storage.googleapis.com` are all outside the egress
allowlist, so `go get` cannot even auto-download a newer toolchain.

Done: `go.mod` (module path + `go 1.26.6` + the pinned require), `.golangci.yml`
with gosec enabled (this module handles the HMAC salt secret), `doc.go` recording
ADR-002. **Not** done: `go.sum`, and the compile check that proves the upstream
`plugin`/`runner` packages import cleanly.

`make go-check` self-skips with this reason while `go.sum` is absent, so the gate
stays honest rather than silently green.

**To unblock:** Go >= 1.26.6 on the build host, then `GOFLAGS=-mod=mod go mod tidy`
inside `barrier/epp`. Worth confirming on Roshan's machine too — T-034 and T-037
onward all need it.

**Plan impact:** HLD §7.1 and §7.11 say "Go 1.24". That should read **Go 1.26.6**.
Small amendment, but it is a stack recommendation, so it is recorded here rather
than silently changed.
