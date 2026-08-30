// Package epp is the PROVENANCE custom Endpoint Picker build.
//
// It is an OUT-OF-TREE module, not a fork of llm-d-router (ADR-002). The
// upstream framework exposes plugin.Register and a package-level plugin.Registry,
// and runner.NewRunner().Run(ctx) — so cmd/epp/main.go can blank-import our
// plugin package (whose init() registers it) and then run upstream's runner
// unmodified. Upgrades are a go.mod bump plus a compile check.
//
// The plugin registered here is "tenant-salt" (LLD §4.3). It has three
// contractual obligations, and omitting any one of them yields a mitigation
// that appears to work and does not:
//
//  1. derive the cache salt by HMAC from authenticated tenant identity —
//     never read it from the client;
//  2. seed the EPP prefix hash chain with it;
//  3. rewrite the OUTBOUND request body's cache_salt to the derived value, so
//     vLLM's own prefix cache partitions identically (ADR-007).
package epp
