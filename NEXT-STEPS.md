# What to do next

**Written:** 2026-09-07, replacing the 2026-08-30 version.
**State:** ATTEST measured and published. BARRIER built, compiling, not yet deployed.

Everything that needed rented hardware is done, for about $2.00. What remains
runs on your own machine, for nothing.

---

## 1. The one substantial claim still unmeasured — S-02

**It now runs itself.** `.github/workflows/barrier.yml` stands up the kind
topology on a GitHub Actions runner, port-forwards the gateway, runs the spike
and uploads `bench/results/` as an artifact. It fires on any push touching
`barrier/**`, or on demand from the Actions tab — where you can also pick the
`hardened` profile instead of `default`.

So the fastest path is: **push, then read the run.** Running it locally is now
optional, and worth doing only if you want to iterate on the spike itself
rather than just get its verdict.

Local instructions kept below, because a reviewer cloning the repo should be
able to reproduce it without a GitHub account.

**Time:** an evening, if you do it by hand. **Cost:** £0. **Needs:** Docker
Desktop with the WSL2 backend, which you already have.

BARRIER's whole attack rests on a premise nobody has tested: **can an ordinary
API caller observe anything that distinguishes a cache hit from a miss?** If the
answer is no on the simulator, FR-B-03 rescopes to an instrumented
demonstration — a finding, not a failure, and one the requirements were written
to survive.

The decision rule was fixed in advance (LLD §7) and travels inside the evidence
file, so the result cannot be rationalised after the fact.

```bash
# prerequisites, once — see docs/RUNBOOK-local.md for the full list
go install sigs.k8s.io/kind@latest github.com/google/ko@latest

cd barrier/deploy/kind
./up.sh default
uv run python -m barrier.attack.spike_s02 --base-url http://localhost:8080
```

**What success looks like:** a verdict in `bench/results/`, either
`ORACLE VIABLE` naming the discriminating signal, or `NO CLIENT-OBSERVABLE
SIGNAL` and a rescope. Either way, **it must reach `docs/design/decisions.md`
before any oracle code is written** — the same discipline as S-03 and the
pre-registered statistics.

Paste the output back and I will take it from there.

---

## 2. The dress rehearsal you never ran

**Time:** 20 minutes, mostly downloads. **Cost:** £0.

```bash
./scripts/rehearse-cpu.sh
```

This became less urgent once the real GPU runs succeeded, but it is still the
only thing that exercises the harness against a real vLLM on hardware you own.
It found three bugs before it had even been executed, by making me read vLLM's
source rather than trust our own stub.

---

## 3. Housekeeping that will bite eventually

**Move the repo off OneDrive.** `C:\Users\rosha\Code\PROVENANCE` or similar.
OneDrive holds file handles inside `.git/objects/`, which is why every push
prompted about failed deletions. `gc.auto 0` suppressed the symptom. The
underlying risk — OneDrive syncing a git object mid-write — is worth removing
from a repository this now has real results in.

---

## What is deliberately *not* on this list

- **More GPU work.** The remaining ATTEST questions — confidence intervals on
  the 2×2, SGLang's Triton backend, dependence on model size and batch shape,
  why vLLM leaves 5 residual vectors — are all real, and none of them changes
  what the project claims. They are follow-ups, not gaps.
- **Polish.** The README carries the numbers, `bench/results/` carries the
  evidence including the runs that were wrong, and the design record is
  committed. Rewriting prose is not what this needs next.

---

## Where things stand

| | |
|---|---|
| Tests | 287 Python, 22 Go, all green |
| Gate | `make check` — ruff, format, mypy strict, pytest, Go build/vet/test |
| Measured | divergence, vLLM invariance + cost, SGLang 2×2 decomposition |
| Built, unmeasured | BARRIER: plugin compiles and is tested; cluster never stood up |
| Spend | ~$2.00 of $20 |

The single highest-value thing you can do is step 1. Everything else is optional.
