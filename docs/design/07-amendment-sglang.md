# Amendment A-01 — adding SGLang

> **Resolution banner — historical record.** This is the amendment as argued, kept
> unrewritten because it is a record of a scope request being reasoned about rather than
> waved through. The amendment was accepted and its narrow version has since run to
> completion. PROVENANCE shipped: phases 0–7 complete, `make check` green at 308 Python
> tests and 22 Go tests. The decomposition §1 argues for was measured — determinism costs
> **18.0% on SGLang, isolated from caching**, against 22.7% on vLLM where the two are
> confounded, and SGLang's deterministic mode leaves 1 distinct logprob vector of 128 where
> vLLM's invariance leaves 5. Current state lives in `STATE.md`, `docs/SHIP-REPORT.md`,
> ADR-011 and ADR-012 in `docs/design/decisions.md`, and `bench/results/`.

**Status:** ACCEPTED 2026-09-07, per the recommendation in §6. See ADR-009 and ADR-010.
**Outcome:** S-03, A-01, A-02 and **A-03** are done — A-03 ran on rented GPU time and its numbers are in `bench/results/sglang-2x2-h100-2026-09-07.md`; A-04 shrank (S-03 came back affirmative) and A-05 is backlogged. Progress is tracked in `docs/design/04-execution-plan.md`.
**Raised:** 2026-09-07, mid-build, against an approved plan.
**Affects:** 01-requirements (D-06, FR set), 02-hld §7, 04-execution-plan (new tasks), decisions.md.

The lifecycle's rule for a scope request that arrives after the plan gate is to
write it down before acting on it. This is that write-up. It is deliberately an
argument with options and costs, not a task list.

---

## 1. Why the question is better than it looks

The obvious reading of "also include SGLang" is *support a second engine* —
breadth for its own sake, the kind of resume line a reviewer discounts on sight.

That is not what the evidence supports. Reading SGLang's and llm-d's sources
turns up a specific, narrow fact that makes SGLang the **control arm** for
ATTEST's central claim rather than a second checkbox:

| | vLLM | SGLang |
|---|---|---|
| Determinism switch | `VLLM_BATCH_INVARIANT=1` (env, engine-wide, read at import) | `--enable-deterministic-inference` (server flag) |
| Backend constraint | CUDA/Triton, compute capability ≥ 8.0 | `--attention-backend` ∈ {flashinfer, fa3, triton} |
| **Prefix / radix caching while deterministic** | **Not integrated upstream** — ATTEST pins it off (D-06) | **Supported on FA3 and Triton**; not on FlashInfer |
| Chunked prefill, CUDA graphs | — | supported on all three backends |

That third row is the whole amendment.

ATTEST's headline deliverable is *the cost of determinism*, a number that does
not appear to be published anywhere. On vLLM that number is unavoidably
**conflated**: turning invariance on also means turning prefix caching off, so
the measurement is "determinism **plus** losing APC", and no amount of care in
the harness separates the two. Every table ATTEST can currently produce carries
that confound, and a careful reader will spot it.

SGLang decomposes it. On FA3 or Triton the radix cache stays on while
determinism is on, which gives a second, cleaner cell:

```
                      caching on        caching off
  nondeterministic       A                  B
  deterministic         C (SGLang only)     D
```

vLLM can produce B and D. SGLang can produce A, B, C and D. **C − D isolates
what the cache is worth under determinism; D − B isolates what determinism
costs on its own.** With vLLM alone, only the sum A − D is observable, and it
gets reported as "the cost of determinism" when it is not.

That is a genuinely stronger result, and it reframes the second engine as
*methodology* rather than coverage. It is also the answer to the reviewer
question ATTEST would otherwise face — "isn't your cost number really the
prefix-cache loss?" — which right now has no good answer.

**This is the argument for the amendment. If it is not persuasive, the rest
does not matter, and SGLang should go to the backlog.**

---

## 2. What BARRIER gains, and what it must not claim

SGLang is a first-class engine in llm-d, not an afterthought. Verified in
`llm-d-router@v0.10.0`:

- `pkg/kvevents/engineadapter/sglang_adapter.go` — a KV-events adapter, selected
  by `engineadapter.EngineTypeSGLang`, alongside the vLLM one
- `pkg/coordinator/connectors/kv/sglang.go` — SGLang disaggregation bootstrap
- `config/manifests/sglang/gpu-deployment.yaml` — labelled
  `llm-d.ai/engine-type: sglang`, on `lmsysorg/sglang:v0.5.12`

So a bank's shared platform running SGLang behind llm-d is a **supported
topology, not a hypothetical** — which means BARRIER's threat model already
applies to it and the write-up currently says nothing about it.

Two things follow, one already acted on and one still open.

### 2.1 Already fixed, independent of this amendment (T-038a, commit `ec00137`)

`ApplySalt` never set `body.Generate.CacheSalt`. That is the pre-tokenized
request shape — vLLM's `/inference/v1/generate` and the path a tokenizing
front-end drives an SGLang pool through — and
`tokenizer.CacheSaltFromBody` reads it. Requests on that surface routed in the
**shared namespace while the hardened profile still reported itself hardened**.

The same commit fixed `body.TokenizedRequest`, a field that does not exist; the
package had never compiled. Both are now covered by tests that interrogate
upstream rather than restate a list, and the plugin builds, vets and passes on
Go 1.26.6. This was a bug in approved scope, so it was fixed rather than
proposed.

### 2.2 Open, and the reason to be careful

> **RESOLVED by S-03 (2026-09-07).** The concern below was well-founded but the
> answer was better than feared: SGLang accepts **`cache_salt`** — llm-d's own
> field name, and a *separate* field from `extra_key` — on `/generate`,
> `/v1/completions`, `/v1/chat/completions` and responses, and it salts the KV
> events it publishes as well as its own radix tree. Obligation 3 is met on
> SGLang with no change to the plugin. See
> `docs/design/spikes/S-03-sglang-cache-salt.md` and ADR-010.
>
> The paragraphs below are left as written, because the reasoning that led to
> running the spike is worth keeping — and because one thing they get wrong is
> instructive: `extra_key` **is** the wrong field, just not for the reason
> guessed here. It namespaces the in-process tree but is not folded into the
> published event hash, so a mitigation built on it would leave the
> routing-derived index shared. It is also the field SGLang's own documentation
> shows for multi-tenancy.

SGLang's radix cache **does** support namespace isolation: `RadixKey` carries an
`extra_key`, populated from `req.extra_key`, and entries with different
`extra_key` values are kept deliberately disjoint. That is structurally the same
control as vLLM's `cache_salt`.

**What is not established is whether SGLang's HTTP API exposes a per-request
field that reaches `extra_key`, and under what name.** The prefix-caching
documentation shows `extra_key` only in Python, at the `RadixKey` level. No
JSON field name has been confirmed.

This matters more than it sounds. BARRIER's mitigation has three obligations:

1. the salt cannot be omitted or forged — **plugin-side, engine-independent**
2. the EPP's routing index is partitioned — **plugin-side, engine-independent**
3. the engine's own KV cache is partitioned — **engine-side, and this is the one in question**

Obligations 1 and 2 hold on SGLang today; they are entirely inside the EPP. If
SGLang has no wire-level route to `extra_key`, then obligation 3 **cannot be
met on SGLang**, and the honest finding is:

> On an SGLang-backed pool, the routing-index channel closes and the engine
> KV-cache channel stays open. The mitigation is half a mitigation there, and
> the deployment posture must say so.

That is a **more interesting result than success**, and it is squarely the kind
of finding an FDE is hired to produce: not "here is a fix", but "here is
precisely which half of the problem this fix closes on which engine, and what
you must do about the other half". It is also exactly the partial fix the
plugin's own docstring warns against shipping unlabelled — so BARRIER must not
publish a mitigation claim covering SGLang until this is resolved either way.

**Therefore: this is a spike (S-03), and its verdict is written down before any
SGLang mitigation code exists — the same discipline as S-02 and the
pre-registered statistics.** A spike that finds "no wire route" is a completed
spike, not a failed one.

---

## 3. What this does *not* buy

Stated plainly, so the amendment cannot be oversold:

- **No new attack.** The channel, the oracle, and the statistics are unchanged.
  SGLang is a second engine behind the same routing layer.
- **No second security claim.** At best BARRIER gains a scoped caveat and a
  cross-engine comparison; at worst, a documented limitation.
- **Nothing about ATTEST's receipts changes.** Model identity still anchors to
  the Hugging Face commit SHA and weight digest, which is engine-agnostic. The
  `EngineState` block gains a variant; the attestation format does not.
  *Correction, post-implementation:* this was half wrong. The predicate went
  **v0.1 → v0.2** — `vllm_version`/`batch_invariant` became
  `engine_version`/`deterministic` plus an explicit `engine` discriminator,
  because reusing vLLM's term for an SGLang run would put a vLLM implementation
  name on a run that never used vLLM's kernels. Under a 0.x major that is a
  breaking change and v0.1 receipts are refused by name. No receipt had been
  published, so nothing was invalidated — but the amendment should not have
  claimed the format was untouched.
- **It costs GPU hours**, and GPU hours are the project's scarcest input. See §5.

---

## 4. What would actually be built

Ordered by value per hour. **Each is independently droppable** — this is not a
package deal, and the recommendation in §6 takes only the top of the list.

| ID | Work | Depends on | Cost |
|---|---|---|---|
| A-01 | `attest/harness/sglang.py` — process lifecycle mirroring `vllm.py`: flags before launch, readiness polled, **resolved config read back and mismatch refused** (D-08 applies unchanged) | — | ~½ day, no GPU |
| A-02 | Generalise `EngineState` over an engine discriminator; keep the receipt schema stable and versioned | A-01 | ~½ day, no GPU |
| A-03 | The 2×2 above as a real matrix: caching × determinism, both engines, one model, existing statistics | A-01, A-02, GPU | GPU session |
| S-03 | **Spike:** does any SGLang wire field reach `RadixKey.extra_key`? Read source, confirm with one live request. Verdict to `decisions.md` before any code | SGLang container | ~2 h, no GPU |
| A-04 | If S-03 finds a route: extend `ApplySalt`/propagation to it, plus a cross-engine hardened profile. If not: write the limitation into the threat model and the deployment posture | S-03 | ~½ day |
| A-05 | Two-engine llm-d topology in the kind chart (`llm-d.ai/engine-type: sglang`, SGLang KV-events adapter) | A-04, cluster | ~1 day |

Two constraints carried in from the existing design:

- **The three-environment split still holds.** A-01, A-02 and S-03 are
  cloud-container work. A-03 needs the rented GPU. A-05 needs the machine that
  can run kind.
- **The negative-result rule still holds.** If SGLang's deterministic mode shows
  no measurable advantage, or S-03 finds no wire route, that is the published
  result, with the same rigour as a positive one.

One honest caveat to carry into any write-up: SGLang has an open report
(sgl-project/sglang#15481) that seeded deterministic inference does not behave
on `/v1/completions`. Whatever is measured must pin the exact SGLang version and
endpoint, and say which were used — the same standard already applied to vLLM.

---

## 5. The case against

> **RESOLVED (2026-09-07, post-build).** Point 1 is no longer true: BARRIER has run. The
> two-tenant kind topology stands up in CI on every push in both profiles, S-02 executed
> (ADR-011, run #12, n=402) and the attack produced data (ADR-012, run #15 — default AUC
> 1.0000, p=9.999e-05, n=80; hardened AUC 0.5000). Point 2 held in principle and cost
> little in practice: the whole 2×2 ran on roughly $2.00 of rented GPU. Points 3 and 4 were
> answered by doing what they demanded — the decomposition is the result, and the SGLang
> arm is measured, not described. The argument below is left as written, because it is the
> reason the amendment was taken narrowly rather than whole, and that was the right call.

Worth stating properly, because it is not weak.

1. **Nothing in BARRIER has run yet.** The plugin now compiles and its unit
   tests pass, but no cluster has been stood up, S-02 has not been executed, and
   the attack has produced no data. Adding a second engine to a workstream with
   zero end-to-end evidence widens the front while the first one is unproven.
2. **GPU hours are the binding constraint.** The 2×2 is roughly double the
   ATTEST GPU session. Spent on SGLang, they are not spent on the vLLM
   measurement that the whole project's headline claim rests on.
3. **Two engines can read as unfocused.** "Also supports SGLang" is a weaker
   line than one deep result. The decomposition argument in §1 is what rescues
   it — and only if the write-up leads with the decomposition rather than the
   coverage.
4. **A shallow SGLang arm is worse than none**, because it invites the question
   "did you actually measure this?" about the vLLM numbers too.

---

## 6. Recommendation

**Accept a narrow version now; defer the rest.**

- **Take S-03 immediately.** It is two hours, needs no GPU and no cluster, and
  it is the one item that can change what BARRIER is allowed to claim. Its
  answer belongs in the threat model whether or not any other SGLang work
  happens, because the SGLang topology is already in scope for the deployment
  BARRIER describes. Deferring it means the write-up either stays silent on a
  supported topology or says something unverified.
- **Take A-01 and A-02 into the current milestone.** Cloud-container work, no
  GPU, and they make the GPU session's shape a decision that can be taken later
  with evidence instead of now without it. Building the harness does not commit
  any GPU minutes.
- **Hold A-03 behind the existing human decision point in T-028.** The ATTEST
  GPU session is already staged as stage 1 → decide → stage 2. Adding the 2×2
  as an explicit stage-2 option costs nothing until that decision is taken, and
  by then stage 1 will have shown whether divergence appears at all. If it does
  not, the whole 2×2 is moot and the hours are saved.
- **Backlog A-04 and A-05.** Both depend on results that do not exist yet —
  A-04 on S-03's verdict, A-05 on a cluster that has never been stood up.

Net effect on the critical path: **none.** S-03, A-01 and A-02 run in the
environment that is otherwise idle waiting on hardware, and no GPU minute is
committed by this amendment.

---

## 7. If accepted, the bookkeeping

1. `decisions.md` gains **ADR-009 — SGLang as ATTEST's control arm for the
   cost-of-determinism decomposition**, recording §1's argument as the reason
   and §5 as the rejected alternative.
2. `01-requirements.md` D-06 is amended: prefix caching is pinned off **for
   vLLM**, and the reason is stated as an upstream integration gap rather than a
   property of determinism — a distinction the current wording elides.
3. `04-execution-plan.md` gains S-03, A-01, A-02 in the current wave; A-03 as a
   T-028 stage-2 option; A-04, A-05 in the backlog.
4. `02-hld.md` §7 records SGLang as a second engine adapter behind the existing
   `EngineClient` seam.
5. `README.md` says nothing about SGLang until S-03 has a verdict and A-03 has
   numbers. The no-unbacked-figures rule applies to this amendment like
   everything else.
