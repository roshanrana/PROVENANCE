# Graph Report - PROVENANCE  (2026-09-10)

## Corpus Check
- 135 files · ~126,915 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1738 nodes · 3300 edges · 115 communities (109 shown, 6 thin omitted)
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 347 edges (avg confidence: 0.52)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `e4da05ed`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 75|Community 75]]
- [[_COMMUNITY_Community 76|Community 76]]
- [[_COMMUNITY_Community 77|Community 77]]
- [[_COMMUNITY_Community 78|Community 78]]
- [[_COMMUNITY_Community 79|Community 79]]
- [[_COMMUNITY_Community 80|Community 80]]
- [[_COMMUNITY_Community 81|Community 81]]
- [[_COMMUNITY_Community 82|Community 82]]
- [[_COMMUNITY_Community 83|Community 83]]
- [[_COMMUNITY_Community 84|Community 84]]
- [[_COMMUNITY_Community 85|Community 85]]
- [[_COMMUNITY_Community 86|Community 86]]
- [[_COMMUNITY_Community 87|Community 87]]
- [[_COMMUNITY_Community 88|Community 88]]
- [[_COMMUNITY_Community 89|Community 89]]
- [[_COMMUNITY_Community 90|Community 90]]
- [[_COMMUNITY_Community 91|Community 91]]
- [[_COMMUNITY_Community 92|Community 92]]
- [[_COMMUNITY_Community 93|Community 93]]
- [[_COMMUNITY_Community 94|Community 94]]
- [[_COMMUNITY_Community 96|Community 96]]
- [[_COMMUNITY_Community 104|Community 104]]
- [[_COMMUNITY_Community 105|Community 105]]

## God Nodes (most connected - your core abstractions)
1. `EngineClient` - 59 edges
2. `Ledger` - 48 edges
3. `EngineError` - 42 edges
4. `SamplingParams` - 40 edges
5. `stub_engine()` - 39 edges
6. `STATE` - 37 edges
7. `EngineState` - 36 edges
8. `Manifest` - 31 edges
9. `MatrixSpec` - 29 edges
10. `EngineLaunchError` - 28 edges

## Surprising Connections (you probably didn't know these)
- `ndarray` --uses--> `InsufficientData`  [INFERRED]
  tests/common/test_stats.py → common/stats/auc.py
- `ndarray` --uses--> `IncomparableMeasurements`  [INFERRED]
  tests/attest/test_cost.py → attest/analysis/cost.py
- `Observation` --uses--> `IncompleteMatrix`  [INFERRED]
  tests/attest/test_divergence.py → attest/analysis/divergence.py
- `Observation` --uses--> `Observation`  [INFERRED]
  tests/attest/test_divergence.py → attest/analysis/divergence.py
- `Any` --uses--> `Observation`  [INFERRED]
  tests/attest/test_divergence.py → attest/analysis/divergence.py

## Import Cycles
- 1-file cycle: `common/runid.py -> common/runid.py`

## Communities (115 total, 6 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.06
Nodes (70): ArgumentParser, Any, EngineState, SamplingParams, Path, Receipt, Path, Any (+62 more)

### Community 1 - "Community 1"
Cohesion: 0.06
Nodes (59): Client, EngineClient, EngineState, Path, Popen, _config(), _mock_client(), SGLang lifecycle — tested as far as a GPU-free machine allows.  Same standard (+51 more)

### Community 2 - "Community 2"
Cohesion: 0.06
Nodes (57): M0 walking skeleton — the seams, tested.  These are integration tests in the s, Fail fast and loudly. A silently degraded run produces a plausible wrong number., FR-A-03 claims bitwise identity; a tolerant digest would weaken the claim., Verify through the CLI, not in-process: the exit-code contract is the deliverabl, D-08. The stub resolves values the caller never asked for; they must appear., Bytes on disk are already canonical, so signature checks are byte-stable., _run(), test_engine_client_reports_unusable_payloads() (+49 more)

### Community 3 - "Community 3"
Cohesion: 0.06
Nodes (56): build_cost_report(), CostReport, load_arms(), _load_jsonl(), main(), Turn a completed run directory into a cost-of-determinism report.  ``attest.an, Split a run directory into (invariance-off, invariance-on) samples., IncomparableMeasurements (+48 more)

### Community 4 - "Community 4"
Cohesion: 0.06
Nodes (52): _attributed_ratio(), DemoError, DemoResult, _index_state(), main(), FR-B-03 — the cross-tenant leak, measured one request at a time.  ADR-011 resc, Send one request and return the match ratio the index attributed to it., Raised when a trial cannot be attributed, rather than guessed at. (+44 more)

### Community 5 - "Community 5"
Cohesion: 0.08
Nodes (45): find_discriminators(), _is_numeric(), main(), measure_numeric_channels(), Probe, probe_once(), S-02 — is there a client-observable routing signal on the simulator?  **This d, Continuous channels that clear the pre-registered bar, by name. (+37 more)

### Community 6 - "Community 6"
Cohesion: 0.09
Nodes (47): CoverageResult, Doc, build_headline(), _check_bars(), _check_facts(), _check_keys(), _check_kpis(), _check_strings() (+39 more)

### Community 7 - "Community 7"
Cohesion: 0.04
Nodes (46): ADR-012 — FR-B-03 MEASURED. Both halves., Blockers, Cost, Current wave, Decisions, Deviations, F-01 — `cache_salt` already exists, and is client-supplied *(2026-08-29)*, F-02 — out-of-tree plugins work; no fork needed *(2026-08-29)* (+38 more)

### Community 8 - "Community 8"
Cohesion: 0.08
Nodes (34): T, T, Context, Decoder, Handle, InferenceRequest, InferenceRequestBody, Plugin (+26 more)

### Community 9 - "Community 9"
Cohesion: 0.08
Nodes (37): Any, Stage 2 spends the remaining GPU budget on one configuration, deeply., NFR-03. Same spec in, same cells out — no clock, no global RNG, no env., Nothing to suppress until a divergence is found; GPU minutes are scarce., Stage 1 must produce its cheapest evidence before spending on 7B., A batch of one cannot be mixed. Emitting those cells would pad the matrix     wi, Two runs with the same fingerprint ran the same experiment., Ties are broken on a stable rendering, not on insertion order. (+29 more)

### Community 10 - "Community 10"
Cohesion: 0.10
Nodes (36): git_state(), iso(), new_run_id(), NotAGitRepositoryError, Path, Run identity and manifest construction.  This module is what makes NFR-01 true b, Directory for *run_id* under *root*. Immutable once written (LLD §5.1)., Raised when git state is requested outside a git repository.      A typed error, (+28 more)

### Community 11 - "Community 11"
Cohesion: 0.09
Nodes (38): _config(), _mock_client(), vLLM lifecycle — tested as far as a GPU-free machine allows.  The launch path, A handler shaped like the real /server_info response., /server_info is registered only under VLLM_SERVER_DEV_MODE.      Without it th, `/server_info`, not `/v1/server_info`; and config_format=json.      Upstream a, The refusal the whole design leans on has to actually fire.      /server_info, Under config_format=text, vllm_config is a string, not an object. (+30 more)

### Community 12 - "Community 12"
Cohesion: 0.05
Nodes (37): 10. Risks and mitigations, 11. Explicitly out of scope, 1. Overview, 2. Architecture style, 3. System context, 4. Components, 5.1 Stores, 5.2 Resumability (+29 more)

### Community 13 - "Community 13"
Cohesion: 0.10
Nodes (35): Any, Canonicalisation and signing.  This is the layer a `verifier-critical` pass woul, RFC 8785 sorts by UTF-16 code units.      Above the BMP the two orders differ: U, bool subclasses int in Python. Getting this wrong emits `1` for `true`., RFC 8785 emits UTF-8 directly rather than \\u escapes., A field that cannot round-trip is not evidence of anything., test_arrays_preserve_order(), test_bools_are_not_treated_as_numbers() (+27 more)

### Community 14 - "Community 14"
Cohesion: 0.16
Nodes (29): Observation, One trial: the bitwise identity of what the engine returned., Tokens *and* logprobs. Two completions can render the same text from         dif, Any, Cell, Client, EngineClient, MatrixSpec (+21 more)

### Community 15 - "Community 15"
Cohesion: 0.15
Nodes (33): _cells(), _execute(), _execute_both_engines(), _full_matrix(), The run driver — resumability is the property that matters.  FR-A-09 exists be, The guard, stated as the property it protects.      Before it existed, this ru, NFR-01: a reader must be able to tell what experiment produced these numbers., The property FR-A-09 exists for: paid GPU work is never redone. (+25 more)

### Community 16 - "Community 16"
Cohesion: 0.11
Nodes (26): Any, Client, EngineState, Path, Popen, test_log_tail_is_included_when_a_log_exists(), _as_mapping(), launch() (+18 more)

### Community 17 - "Community 17"
Cohesion: 0.06
Nodes (30): 01 — Requirements, 0. Changes since v0.1, 10. Open questions for the gate, 1. Purpose, 2. Decisions taken at intake, 3.1 Project level, 3.2 Per-workstream tiers, 3. Success definition (+22 more)

### Community 18 - "Community 18"
Cohesion: 0.10
Nodes (19): EngineClient, vLLM omits token_ids unless the request asks for them.      ``CompletionRespon, The diagnostic has to name the cause.      'unusable completion payload: token, vLLM types token_logprobs as ``list[float | None]`` and emits None     wherever, test_a_response_without_token_ids_is_refused_by_name(), test_null_logprobs_are_refused_rather_than_coerced(), test_the_request_opts_in_to_token_ids(), EngineClient (+11 more)

### Community 19 - "Community 19"
Cohesion: 0.17
Nodes (27): analyse_run(), IncompleteMatrix, Read one cell's raw JSONL. Malformed lines are an error, not a shrug., Summarise a completed run.      Refuses an incomplete or partially failed matrix, Refusal to summarise a run that did not finish. Maps to exit code 8., read_observations(), Path, NFR-17. An absent effect is a finding, stated plainly, not a silent gap. (+19 more)

### Community 20 - "Community 20"
Cohesion: 0.12
Nodes (25): Statistics — the tests a `verifier-critical` pass would demand.  Checked again, NFR-05, pinned. If a threshold moved, the project is marking its own homework., z_{0.975}=1.95996, z_{0.8}=0.84162 -> n = 2(2.80158)^2 = 15.7 -> 16., Every score identical carries no information. Ties count as half.      A pairw, Reference check against an independent implementation., Ties are where implementations diverge, so they get their own reference check., AUC is rank-based: units must not matter (seconds vs milliseconds)., test_all_ties_is_exactly_one_half() (+17 more)

### Community 21 - "Community 21"
Cohesion: 0.19
Nodes (9): Any, Path, CellRecord, Ledger, Write the initial ``pending`` records. Idempotent: seeding twice is a no-op., All transitions, in order. A truncated final line is dropped, not fatal., Current state per cell — the last transition wins., Cells still to run: ``pending`` and ``running`` (the latter interrupted). (+1 more)

### Community 22 - "Community 22"
Cohesion: 0.24
Nodes (23): Every row of the LLD §5 exit-code taxonomy gets a test.  The point of the taxono, Tampering must be distinguishable from corruption., The one sanctioned degradation: offline still gets an answer., Canonicalisation is recomputed from the parsed document, not the bytes.      A r, run(), test_bad_signature_exits_two(), test_edited_output_exits_three_not_four(), test_hub_unreachable_exits_five_and_says_offline_passed() (+15 more)

### Community 23 - "Community 23"
Cohesion: 0.16
Nodes (17): Labels, Scores, Labels, Scores, Any, Labels, Scores, Labels (+9 more)

### Community 24 - "Community 24"
Cohesion: 0.14
Nodes (22): With 3 positives, pooled resampling would sometimes draw none at all., The two flags are deliberately not complements.      A real-but-weak signal mu, A published verdict must carry the bar it was judged against., _separated(), test_bootstrap_differs_across_seeds(), test_bootstrap_is_deterministic_for_a_fixed_seed(), test_hardened_result_is_judged_at_chance(), test_interval_brackets_the_point_estimate() (+14 more)

### Community 25 - "Community 25"
Cohesion: 0.17
Nodes (15): esc(), fig_decomposition(), fig_divergence(), fig_frb03(), fig_s02_power(), _interval_panel(), main(), Any (+7 more)

### Community 26 - "Community 26"
Cohesion: 0.10
Nodes (19): 0. Spike results, 1. Repository layout, 2. Conventions, 3. Configuration matrix, 4.1 Attestation receipt *(FR-A-05, FR-A-06)*, 4.2 `common/stats` API *(NFR-05, ADR-003)*, 4.3 Tenant-salt plugin *(FR-B-05, revised per S-04)*, 4.4 Attack oracle interface — **FROZEN; S-02 returned negative (ADR-011)** (+11 more)

### Community 27 - "Community 27"
Cohesion: 0.11
Nodes (18): _divergence(), Every headline number in the prose must still match the measurements.  CLAUDE., The strongest number in the repository is also the easiest to overstate., The JSON is documentation; `common.stats.decision` is the enforcement.      Th, Counted, not asserted from memory — the README got this wrong twice., A number whose source file has been renamed away is unverifiable., Figures are regenerated by script, never hand-edited (CLAUDE.md).      Re-runs, 18.0% is D/B. Quoting it as anything else republishes the confound. (+10 more)

### Community 28 - "Community 28"
Cohesion: 0.21
Nodes (18): Any, The same document, differently ordered, must verify under one signature., One ULP apart must not share a signature., test_any_change_breaks_verification(), test_float_precision_survives_signing(), test_is_test_key_recognises_both_halves(), test_sign_and_verify_round_trip(), test_test_key_is_refused_by_default() (+10 more)

### Community 29 - "Community 29"
Cohesion: 0.19
Nodes (17): Path, 0600 from creation — never world-readable, even briefly (NFR-14)., test_key_round_trips_through_disk(), test_private_key_is_written_unreadable_to_others(), test_reading_a_non_ed25519_key_is_rejected(), Ed25519PublicKey, public_bytes(), ed25519 signing and verification for attestation receipts.  ADR-005: offline-ver (+9 more)

### Community 30 - "Community 30"
Cohesion: 0.17
Nodes (16): Re-running the entry command must not duplicate the matrix., An interrupted `running` cell must be re-run; a `done` cell must not., Excluded from analysis, and never retried into the dataset (HLD §8.4).      Retr, A power cut mid-write costs the last transition, not the run., Resume works across processes — the ledger is the state, not the object., test_counts_and_completion(), test_empty_ledger_reads_as_empty(), test_failed_cells_are_never_resumed() (+8 more)

### Community 31 - "Community 31"
Cohesion: 0.19
Nodes (8): CellSummary, DivergenceReport, Divergence analysis — raw run output to the tables FR-A-01/03/04 publish.  Two r, The table FR-A-01 publishes. Regenerated by script, never hand-edited., True if any invariance-off cell produced more than one completion.          If t, True if every invariance-on cell is bitwise identical across trials.          Va, to_markdown_table(), Any

### Community 32 - "Community 32"
Cohesion: 0.16
Nodes (16): Any, The guard that makes a two-engine stage 2 honest.      batch_invariant is an e, An engine that cannot be read is refused, not waved through.      The first ve, ADR-009's engine-neutral determinism, made executable.      The cell says batc, test_a_cell_is_skipped_when_the_engine_contradicts_it(), test_an_unreachable_engine_does_not_silently_pass_the_guard(), test_the_guard_reads_sglangs_endpoint_too(), CellParams (+8 more)

### Community 33 - "Community 33"
Cohesion: 0.12
Nodes (16): 10. Responsible disclosure, 1. The scenario, 2. What llm-d actually does, 3. Actors and trust boundaries, 4. The attacker, 5. The three failure modes, 6.1 The routing index — approximate path *(default)*, 6.2 The engine cache — precise path (+8 more)

### Community 34 - "Community 34"
Cohesion: 0.12
Nodes (16): Architecture, At a glance, ATTEST — reproducibility as a model-risk control, BARRIER — prefix-cache locality as a cross-tenant leak, How this is built, License, On negative results, On statistics (+8 more)

### Community 35 - "Community 35"
Cohesion: 0.20
Nodes (13): Any, Client, test_http_error_becomes_hub_unreachable(), test_resolution_extracts_commit_sha_and_lfs_digest(), test_weights_without_lfs_digest_is_unreachable_not_silently_empty(), _extract(), HubIdentity, HubUnreachable (+5 more)

### Community 36 - "Community 36"
Cohesion: 0.14
Nodes (13): 00 — Upstream Verification Findings, 1.1 What is confirmed, 1.2 What is stale in the brief, 1.3 Constraints the design must absorb, 1.4 Performance context, 1. vLLM batch invariance (ATTEST dependency), 2.1 Naming and repo layout, 2.2 Plugin framework — confirmed shape (+5 more)

### Community 37 - "Community 37"
Cohesion: 0.17
Nodes (11): float64, NDArray, One outlier should move SD far more than IQR — which is why both are kept., test_noise_floor_refuses_degenerate_input(), test_noise_floor_reports_iqr_as_well_as_sd(), test_noise_floor_summarises_dispersion(), measure_noise_floor(), NoiseFloor (+3 more)

### Community 38 - "Community 38"
Cohesion: 0.19
Nodes (5): PROVENANCE — Showcase, Questions this project answers, and where, Ten minutes, Things worth noticing, What it does not claim

### Community 39 - "Community 39"
Cohesion: 0.15
Nodes (13): ADR-001 — Monorepo of CLIs, no services, ADR-002 — Out-of-tree Go module rather than a fork, ADR-003 — Own the statistical test rather than import it, ADR-004 — Helm with two values files as the mitigation's presentation, ADR-005 — ed25519 with in-toto predicate; sigstore deferred, ADR-006 — Strip the identity header at the proxy, and fail closed in the plugin, ADR-007 — The salt must be propagated to the engine, not only the EPP index, ADR-008 — The Go toolchain block is retired, not designed around (+5 more)

### Community 40 - "Community 40"
Cohesion: 0.15
Nodes (12): 1. What this is and why it exists, 2.1 Workstream A — ATTEST, 2.2 Workstream B — BARRIER, 2. Problem statements, 3. Scope and deliverables, 4. Environment and constraints, 5. What "done" looks like, 6. How I want to work with you (+4 more)

### Community 41 - "Community 41"
Cohesion: 0.18
Nodes (10): 05 — Orchestration Runbook, 1. Roles and their settings, 2. Why this saves context (the actual mechanism), 3. The loop, 4. Wave dispatch, concretely, 5. Failure handling, 6. What Roshan sees, 7. Prerequisites before the first dispatch (+2 more)

### Community 42 - "Community 42"
Cohesion: 0.18
Nodes (10): 1. Why the question is better than it looks, 2.1 Already fixed, independent of this amendment (T-038a, commit `ec00137`), 2.2 Open, and the reason to be careful, 2. What BARRIER gains, and what it must not claim, 3. What this does *not* buy, 4. What would actually be built, 5. The case against, 6. Recommendation (+2 more)

### Community 43 - "Community 43"
Cohesion: 0.18
Nodes (10): 06 — Codex Build Runbook, 1. How Codex differs, and what that changes, 2. Roles and profiles, 3. Why this keeps context small, 4. The loop, 5. Wave 2, concretely, 6. Failure handling, 7. What Roshan sees (+2 more)

### Community 44 - "Community 44"
Cohesion: 0.18
Nodes (10): Amendment A-01 — SGLang (accepted 2026-09-07), Dependency notes, Execution Plan — PROVENANCE, Gate map, Milestones, Pack coverage, Risk this adds, Task table (+2 more)

### Community 45 - "Community 45"
Cohesion: 0.31
Nodes (10): clip(), load(), main(), md_cell(), Path, Render metrics/headline.json into a results card.  Outputs:   docs/assets/met, render_markdown(), render_svg() (+2 more)

### Community 46 - "Community 46"
Cohesion: 0.18
Nodes (10): Acceptance criteria, Context, Contracts to honor, File scope, Goal, Handoff notes, Out of scope, Suggested steps (+2 more)

### Community 47 - "Community 47"
Cohesion: 0.18
Nodes (10): Acceptance criteria, Context, Contracts to honor, File scope, Goal, Handoff notes, Out of scope, Suggested steps (+2 more)

### Community 48 - "Community 48"
Cohesion: 0.18
Nodes (10): Acceptance criteria, Context, Contracts to honor, File scope, Goal, Handoff notes, Out of scope, Suggested steps (+2 more)

### Community 49 - "Community 49"
Cohesion: 0.18
Nodes (10): Acceptance criteria, Context, Contracts to honor, File scope, Goal, Handoff notes, Out of scope, Suggested steps (+2 more)

### Community 50 - "Community 50"
Cohesion: 0.18
Nodes (10): Acceptance criteria, Context, Contracts to honor, File scope, Goal, Handoff notes, Out of scope, Suggested steps (+2 more)

### Community 51 - "Community 51"
Cohesion: 0.18
Nodes (10): Acceptance criteria, Context, Contracts to honor, File scope, Goal, Handoff notes, Out of scope, Suggested steps (+2 more)

### Community 52 - "Community 52"
Cohesion: 0.20
Nodes (9): 1. The CPU dress rehearsal (~20 min, mostly downloads), 2. The BARRIER cluster (~30 min first time), Local runbook — everything that does not need a GPU, Prerequisites, Run it, Run it, Then the spike that is actually blocking BARRIER, What it is for (+1 more)

### Community 53 - "Community 53"
Cohesion: 0.20
Nodes (10): 1. Why the question is better than it looks, 2.1 Already fixed, independent of this amendment (T-038a, commit `ec00137`), 2.2 Open, and the reason to be careful, 2. What BARRIER gains, and what it must not claim, 3. What this does *not* buy, 4. What would actually be built, 5. The case against, 6. Recommendation (+2 more)

### Community 54 - "Community 54"
Cohesion: 0.20
Nodes (9): 1. The CPU dress rehearsal (~20 min, mostly downloads), 2. The BARRIER cluster (~30 min first time), Local runbook — everything that does not need a GPU, Prerequisites, Run it, Run it, Then the two measurements, which are already answered, What it is for (+1 more)

### Community 55 - "Community 55"
Cohesion: 0.22
Nodes (8): Definition of done, per task, Evidence discipline, Non-negotiables, PROVENANCE — Agent Instructions, Start here, every session, Toolchain, What is not yours to run, Where things are

### Community 56 - "Community 56"
Cohesion: 0.22
Nodes (9): The add-one correction. A reported p of exactly 0 is not honesty, it is     run, An inverted oracle is still an oracle: AUC well below 0.5 must be significant., test_no_signal_gives_a_large_p_value(), test_p_value_is_never_zero(), test_permutation_is_deterministic_for_a_fixed_seed(), test_strong_signal_gives_a_small_p_value(), test_test_is_two_sided(), permutation_p() (+1 more)

### Community 57 - "Community 57"
Cohesion: 0.22
Nodes (9): Architecture in one screen, ATTEST: reproducibility as a control, BARRIER: prefix-cache locality as a leak, Further reading, PROVENANCE — Overview, The setting, What has been demonstrated, and what has not, Where it sits among the other projects (+1 more)

### Community 58 - "Community 58"
Cohesion: 0.32
Nodes (8): summarise_cell(), _obs(), The bits move before the words do.      Two completions can render identical tex, test_differing_tokens_are_counted_as_divergence(), test_empty_cell_is_refused(), test_identical_tokens_with_differing_logprobs_is_still_divergence(), test_identical_trials_are_one_completion(), Observation

### Community 59 - "Community 59"
Cohesion: 0.46
Nodes (7): runpod-stage1.sh script, cleanup(), emit_and_exit(), fail(), say(), VLLM_BATCH_INVARIANT, VLLM_SERVER_DEV_MODE

### Community 60 - "Community 60"
Cohesion: 0.25
Nodes (7): A-03 — the caching × determinism decomposition, on SGLang, Cost, The 2×2, The comparison that makes this interesting, The decomposition, Two things worth reading carefully, What this does not establish

### Community 61 - "Community 61"
Cohesion: 0.25
Nodes (7): 1. What is claimed, and what backs it, 2. What went wrong, and what caught it, 3. Gates, 4. What a reviewer should check first, 5. What is not done, 6. Cost, Ship report

### Community 62 - "Community 62"
Cohesion: 0.25
Nodes (7): Read these, in this order, START HERE, The standard this project is held to, The two risks the design carried, Three findings that shaped the design, What ran where, What this project is

### Community 63 - "Community 63"
Cohesion: 0.25
Nodes (7): 1. Partially-shared prefixes — the experiment that makes the result subtle, 2. FR-B-09 — the client-observable oracle, on real vLLM, 3. The ATTEST loose ends, Nothing here is required, The three follow-ups, in the order I would do them, What is deliberately not on this list, What to do next

### Community 64 - "Community 64"
Cohesion: 0.25
Nodes (7): Read these, in this order, START HERE, The standard this project is held to, The two risks the design carried, Three findings that shaped the design, What ran where, What this project is

### Community 65 - "Community 65"
Cohesion: 0.29
Nodes (6): Evidence discipline, Non-negotiables, PROVENANCE, Start here, every session, Toolchain, Where things are

### Community 66 - "Community 66"
Cohesion: 0.29
Nodes (6): Evidence discipline, Non-negotiables, PROVENANCE, Start here, every session, Toolchain, Where things are

### Community 67 - "Community 67"
Cohesion: 0.29
Nodes (6): Conditions, Cost of producing it, The correction, The cost of determinism — measured, with intervals, The figure, What this still does not establish

### Community 68 - "Community 68"
Cohesion: 0.29
Nodes (6): 1. The one substantial claim still unmeasured — S-02, 2. The dress rehearsal you never ran, 3. Housekeeping that will bite eventually, What is deliberately *not* on this list, What to do next, Where things stand

### Community 69 - "Community 69"
Cohesion: 0.29
Nodes (6): 1. The chain, end to end, 2. The part that decides BARRIER's routing claim, 3. What this changes upstream of us, 4. What is *not* established, and must not be claimed, S-03 — Does any SGLang wire field reach the radix cache's namespace key?, Verdict

### Community 70 - "Community 70"
Cohesion: 0.29
Nodes (6): Cost, and what the shakedown bought, Hardware and configuration, Next, Stage 1 — divergence observed on an A40, The result, What this does and does not establish

### Community 71 - "Community 71"
Cohesion: 0.29
Nodes (6): Cost, Hardware and configuration, How the two arms were kept honest, Stage 2 — batch invariance eliminates the divergence, The result, What this does not establish

### Community 72 - "Community 72"
Cohesion: 0.29
Nodes (7): 1. Batched inference is not reproducible, and the fix is partial, 2. The cost of determinism is not what the obvious experiment measures, 3. The cross-tenant leak, and the mitigation closing it, 4. What a pre-registered rule is actually for, Results, The runs that were wrong, What is not measured, stated as plainly as what is

### Community 73 - "Community 73"
Cohesion: 0.29
Nodes (7): 1. What is claimed, and what backs it, 2. What went wrong, and what caught it, 3. Gates, 4. What a reviewer should check first, 5. What is not done, 6. Cost, Ship report

### Community 74 - "Community 74"
Cohesion: 0.29
Nodes (6): Budget, Hard requirement, The GPU session, The two phases, and why they use different cards, What stage 1 does and does not answer, Why the run is a batch job, not an interactive session

### Community 75 - "Community 75"
Cohesion: 0.29
Nodes (6): Output, Per-criterion verdict, Role: VERIFIER, Standing checklist, beyond the pack's own criteria, What you read — and what you deliberately do not, You never fix code

### Community 76 - "Community 76"
Cohesion: 0.29
Nodes (6): Contracts are frozen, Finishing, Read order — fixed, no deviation, Role: WORKER, Scope is absolute, Two-strike rule

### Community 77 - "Community 77"
Cohesion: 0.29
Nodes (6): 1. The chain, end to end, 2. The part that decides BARRIER's routing claim, 3. What this changes upstream of us, 4. What is *not* established, and must not be claimed, S-03 — Does any SGLang wire field reach the radix cache's namespace key?, Verdict

### Community 78 - "Community 78"
Cohesion: 0.33
Nodes (5): Output, Per-criterion verdict, Standing checklist, beyond the pack's own criteria, What you read — and what you deliberately do not, You never fix code

### Community 79 - "Community 79"
Cohesion: 0.33
Nodes (5): Contracts are frozen, Finishing, Read order — fixed, and you do not deviate, Scope is absolute, Two-strike rule

### Community 80 - "Community 80"
Cohesion: 0.33
Nodes (6): Sanity: the NFR-05 bar must be reachable at a trial count we can afford., test_required_trials_for_auc_at_the_pre_registered_bar_is_modest(), test_required_trials_for_auc_decreases_as_the_effect_grows(), test_required_trials_for_auc_refuses_chance_or_certainty(), Positives needed to distinguish *target_auc* from chance (Hanley-McNeil).      U, required_trials_for_auc()

### Community 81 - "Community 81"
Cohesion: 0.33
Nodes (6): 1. The receipt pipeline (`attest/receipt/`), 2. The measurement harness (`attest/harness/`), 3. Pre-registered statistics (`common/stats/`), 4. The tenant-salt plugin (`barrier/epp/`), 5. The threat model (`docs/threat-model.md`), Feature tour

### Community 82 - "Community 82"
Cohesion: 0.40
Nodes (5): main(), _one(), Any, Client, Measure one cell of the A-03 2x2 against a live SGLang engine.  Deliberately n

### Community 83 - "Community 83"
Cohesion: 0.40
Nodes (5): _load_jsonl(), main(), Any, Path, Compress a stage-1 run into something a log stream can actually carry.  The fi

### Community 84 - "Community 84"
Cohesion: 0.50
Nodes (3): main(), _mean(), Turn the four A-03 cells into the decomposition ADR-009 exists for.  The point

### Community 85 - "Community 85"
Cohesion: 0.40
Nodes (4): If the push is rejected, One command to publish everything, Verifying, if you want to, What it will publish

### Community 86 - "Community 86"
Cohesion: 0.40
Nodes (4): Method, Output, Role: SPIKE, Time box

### Community 87 - "Community 87"
Cohesion: 0.50
Nodes (3): Method, Output, Time box

### Community 88 - "Community 88"
Cohesion: 1.00
Nodes (3): runpod-sglang-2x2.sh script, run_cell(), say()

### Community 89 - "Community 89"
Cohesion: 0.50
Nodes (4): A 95% interval must contain the truth about 95% of the time.      This is the, test_bootstrap_interval_is_calibrated(), bootstrap_coverage(), Fraction of ``trials`` null datasets whose bootstrap interval contains 0.5.

### Community 90 - "Community 90"
Cohesion: 0.50
Nodes (3): Adversarial reading, Role: VERIFIER-CRITICAL, Where the real risk lives

### Community 91 - "Community 91"
Cohesion: 0.50
Nodes (3): InsufficientData, AUC and its bootstrap confidence interval.  Implemented here rather than importe, Both classes must be present for AUC to be defined.

## Knowledge Gaps
- **441 isolated node(s):** `Any`, `Client`, `Engine`, `SignedStatement`, `up.sh script` (+436 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `SGLangConfigError` connect `Community 1` to `Community 0`, `Community 18`, `Community 14`, `Community 6`?**
  _High betweenness centrality (0.085) - this node is a cross-community bridge._
- **Why does `EngineClient` connect `Community 18` to `Community 32`, `Community 1`, `Community 0`, `Community 2`, `Community 14`, `Community 16`?**
  _High betweenness centrality (0.063) - this node is a cross-community bridge._
- **Why does `EngineError` connect `Community 14` to `Community 32`, `Community 1`, `Community 2`, `Community 0`, `Community 16`, `Community 18`, `Community 29`?**
  _High betweenness centrality (0.046) - this node is a cross-community bridge._
- **Are the 35 inferred relationships involving `EngineClient` (e.g. with `Any` and `Cell`) actually correct?**
  _`EngineClient` has 35 INFERRED edges - model-reasoned connections that need verification._
- **Are the 26 inferred relationships involving `Ledger` (e.g. with `CellSummary` and `DivergenceReport`) actually correct?**
  _`Ledger` has 26 INFERRED edges - model-reasoned connections that need verification._
- **Are the 31 inferred relationships involving `EngineError` (e.g. with `Any` and `Cell`) actually correct?**
  _`EngineError` has 31 INFERRED edges - model-reasoned connections that need verification._
- **Are the 23 inferred relationships involving `SamplingParams` (e.g. with `Any` and `EngineState`) actually correct?**
  _`SamplingParams` has 23 INFERRED edges - model-reasoned connections that need verification._