module github.com/roshanrana/provenance/barrier/epp

// llm-d-router v0.10.0 declares `go 1.26.6`. See BLOCKED note in
// docs/tasks/T-003-go-scaffold.md — this module cannot be resolved on a
// toolchain older than that.
go 1.26.6

require github.com/llm-d/llm-d-router v0.10.0
