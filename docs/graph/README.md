# Code graph

PROVENANCE carries a queryable code knowledge graph, built by
[graphify](https://pypi.org/project/graphifyy/) from a tree-sitter AST pass over the repo — no
LLM, no network call, offline and reproducible. It answers "what depends on this?", "how do A
and B connect?" and "what is X?" with file:line citations, in a few hundred tokens, where a grep
sweep would cost thousands. Agents working in this repo should query it before opening files for
a task; see the rule at the top of `CLAUDE.md`.

## Build and query

```bash
graphify update .                          # rebuild the graph (AST only, ~6s, no API key needed)
graphify query "<question>" --budget 800   # BFS traversal scoped to a question
graphify explain "<name>"                  # a node and its immediate neighbors
graphify path "<A>" "<B>"                  # shortest relation path between two symbols
graphify affected "<name>" --depth 2       # reverse traversal: what breaks if this changes
```

`graphify install --project` (not run in CI, and not committed) additionally registers local
PreToolUse hooks that remind an interactive session to query the graph before a Read or grep —
opt in per machine.

## Current graph

Built 2026-09-10 in ~6.5s: **1,738 nodes**, **3,300 edges**, **115 communities**.

## Three real queries

### `graphify explain "Receipt"`

```
Node: Receipt
  ID:        attest_harness_skeleton_py_receipt
  Source:    attest/harness/skeleton.py L131
  Type:      code
  Community: 0
  Degree:    9

Connections (9):
  --> EngineClient [uses] [INFERRED]
  --> Ledger [uses] [INFERRED]
  --> SamplingParams [uses] [INFERRED]
  --> Manifest [uses] [INFERRED]
  --> Receipt [uses] [INFERRED]
  <-- run_skeleton() [calls] [EXTRACTED]
  --> ModelIdentity [uses] [INFERRED]
  --> RunRef [uses] [INFERRED]
  <-- _emit_receipt() [references] [EXTRACTED]
```

Anchors the attestation receipt (`attest/receipt/`) to the one place it is actually assembled
end-to-end, `attest/harness/skeleton.py`'s demo driver — the fastest way into the receipt
pipeline for a newcomer, faster than reading `schema.py` cold.

### `graphify path "RequestHeader" "DeriveSalt"`

```
Shortest path (2 hops):
  .RequestHeader() --calls [EXTRACTED]--> .saltFor() --calls [INFERRED]--> DeriveSalt()
```

Traces the router/EPP plugin (`barrier/epp/plugin/plugin.go`, the `TenantSalt.RequestHeader`
hook llm-d calls per request) to the tenant-salt derivation (`barrier/epp/plugin/salt.go`,
`DeriveSalt`) through the one intermediate call, `saltFor`. Confirms there is no other path in
or out of the salting logic.

### `graphify affected "subject_digest" --depth 2`

```
Affected nodes for subject_digest()
Relations: calls, references, imports, imports_from, re_exports, inherits, extends, implements, uses, mixes_in, embeds
Depth: 2
- test_receipt_schema.py [imports] tests/attest/test_receipt_schema.py:L1
- test_statement_has_the_frozen_shape() [calls] tests/attest/test_receipt_schema.py:L66
- .from_statement() [calls] attest/receipt/schema.py:L333
- .to_statement() [calls] attest/receipt/schema.py:L313
```

`subject_digest` is part of the frozen receipt schema contract (`docs/design/03-lld.md` §4). The
blast radius is small and entirely local to `attest/receipt/schema.py` plus its test — evidence
that the contract is genuinely load-bearing in only one place, not scattered.

**One rough edge:** `graphify affected "Receipt" --depth 2` returns `No unique node match for
Receipt` — the bare class name collides with the `Receipt` variable in `skeleton.py` above. Use
a more specific token (a method or field name, as in `subject_digest` above) when a class name
alone is ambiguous.

## What is excluded

`.graphifyignore` keeps the graph about the code that is actually reasoned over:
`.venv/`, `graphify-out/` (self-reference), `bench/results/` (immutable measurement output, not
source), `docs/assets/` (rendered figures), the various tool caches
(`.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`, `__pycache__/`), `node_modules/` (none in this
repo today, kept for parity with graphify's defaults), and `_to_delete/`.

## What is committed vs. generated

| Path | Committed? |
|---|---|
| `graphify-out/GRAPH_REPORT.md` | Yes — human-readable map of communities and cross-file links |
| `graphify-out/graph.json`, `graph.html`, `cache/`, `manifest.json` | No — gitignored, rebuilt in seconds with `graphify update .` |
| `.claude/skills/graphify/` | Yes — the agent-facing skill, so any Claude Code session in this repo can query the graph |
| `.claude/settings.json` (PreToolUse hooks) | No — local opt-in only, not this repo's policy for every clone |

## Shipyard integration

Implementers query the graph before opening files for a task pack; Verifiers run
`graphify affected` on every symbol a diff touches and treat anything outside the pack's scope
as a finding.
