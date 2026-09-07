# What to do next

**Written:** 2026-09-07, replacing the version written earlier the same day —
which opened with "the one substantial claim still unmeasured" and named S-02.
That claim, and the two behind it, have since been measured.

**State: both workstreams have their headline result. Nothing is blocked.**

---

## Nothing here is required

The previous three versions of this file each had a step 1 that had to happen
before the project could claim anything. This one does not. Every claim in the
README and the ship report traces to committed raw output, or is marked as not
established.

| | result | where |
|---|---|---|
| ATTEST | determinism costs **18.0%** on SGLang, isolated from prefix caching; 22.7% on vLLM, confounded with it | `bench/results/sglang-2x2-h100-2026-09-07.md` |
| BARRIER attack | routing index leaks across tenants — **AUC 1.0000**, p=9.999e-05, n=80 | ADR-012, `bench/results/frb03-run15-2026-09-07.md` |
| BARRIER mitigation | tenant salt closes it — **AUC 0.5000**, at chance, same schedule | same |
| S-02 | no client-observable oracle on the simulator | ADR-011 |

BARRIER's numbers regenerate on every push, both profiles, on GitHub-hosted
runners. There is nothing to run locally to reproduce them — read the CI log.

---

## The three follow-ups, in the order I would do them

### 1. Partially-shared prefixes — the experiment that makes the result subtle

**Time:** an hour of code, minutes of CI. **Cost:** £0.

FR-B-03 measures identical-versus-disjoint prompts, so the match ratio is 1.0 or
0.0 and the AUC is 1.0000 with a degenerate interval. That is a clean result and
a slightly artificial one.

The realistic case is a **shared system prompt with differing tails** — which is
what actually happens in a bank, and what prefix caching exists to exploit. The
match ratio becomes continuous, the interval stops being degenerate, and the
interesting question becomes *how much* shared prefix an attacker needs before
the oracle is reliable.

Extend `barrier/attack/demo_frb03.py` with a shared-prefix fraction parameter and
sweep it. The instrument and the decision rule already work.

### 2. FR-B-09 — the client-observable oracle, on real vLLM

**Time:** an evening. **Cost:** a few dollars of rented GPU.

ADR-011 established that the *simulator* offers a client nothing, and said so as
a property of the simulator (D-01: it does not vary TTFT on cache hit versus
miss) rather than of llm-d. Real vLLM does vary. Whether that difference is large
enough to clear the pre-registered bar from outside the cluster is the open
question, and it is the one that would turn BARRIER from an operator-visible
finding into an attacker-visible one.

The GPU harness, the statistics and the decision rule all exist. What is missing
is a vLLM-backed pool in the kind topology instead of the simulator.

### 3. The ATTEST loose ends

None of these change what the project claims:

- Confidence intervals on the SGLang 2×2. The vLLM cost figure has a bootstrap
  interval; the 2×2 ratios are point estimates over 128 trials per cell.
- SGLang's Triton backend. FA3 was used throughout; the compatibility matrix says
  Triton also supports determinism with the radix cache, and whether the cost
  differs is unmeasured.
- **Why vLLM's batch-invariant mode leaves 5 of 128** while SGLang's leaves 1.
  This is the most interesting unanswered question in the repository.

---

## What is deliberately not on this list

- **Polish.** The README carries the numbers, `bench/results/` carries the
  evidence including the runs that were wrong, and the design record is
  committed.
- **More engines.** SGLang is a control arm, not coverage. A third engine would
  add breadth to a project whose value is depth.
- **Making the finding record shorter.** Fourteen defects are recorded, four of
  them guards that contained the defect they were written to catch, and one a
  claim this project made and then withdrew. That record is the most credible
  thing here precisely because nobody would invent it.
