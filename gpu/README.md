# The GPU session

Everything here runs on rented hardware. Nothing in this directory is needed to
build, test or read the project — it exists because ATTEST's central claim
cannot be measured on any machine this project owns.

## Why the run is a batch job, not an interactive session

The pod is launched through RunPod's MCP server, which manages **infrastructure**
— create, start, stop, log — and gives no shell inside the container. That
constraint pushed the design somewhere better than an SSH session would have:

`runpod-stage1.sh` is self-contained. It announces every step, fails loudly,
and prints its results to stdout as a gzipped base64 payload between markers,
because the pod's log stream is the only channel out. It cannot be left running
by accident, and it cannot half-succeed quietly.

That is the same discipline `barrier/deploy/kind/up.sh` already follows, and for
the same reason: nobody is watching.

## The two phases, and why they use different cards

**Phase 1 — shakedown, on an A40.** This code has never executed a single CUDA
kernel. The first contact with a real GPU will find bugs; the CPU rehearsal
(`scripts/rehearse-cpu.sh`) already found three before we got here. Debugging at
$0.49/hr instead of $3.49/hr is the entire argument. The A40 is Ampere GA102,
compute capability 8.6, 48 GB, datacenter-grade, and RunPod carries it in Secure
Cloud only — no third-party hosts, which matters for a project about provenance.

**Phase 2 — the published run, on an H100 SXM.** Once the harness runs clean,
the numbers that get written down are produced on hardware a regulated
institution would actually deploy. Two concrete reasons beyond credibility:

* SGLang's **FA3 attention backend is Hopper-only**, and FA3 is the one backend
  that supports every feature in SGLang's compatibility matrix — CUDA graphs,
  chunked prefill, radix cache, non-greedy sampling. A-03's caching ×
  determinism 2×2 is strongest there, and Triton on the same card gives a
  cross-check.
* A cost-of-determinism figure measured on a consumer card invites the obvious
  objection. One measured on an H100 does not.

Secure Cloud is chosen over Community Cloud for phase 2 even though it costs
more: a published number should name the operator of the machine that produced
it.

## Budget

| | Card | Rate | Expected | Cost |
|---|---|---|---|---|
| Phase 1 | A40 (secure) | $0.49/hr | 2–3 h incl. debugging | ~$1.50 |
| Phase 2 | H100 SXM (secure) | $3.49/hr | ~2 h clean | ~$7 |

Comfortably inside $20, with room for phase 1 to go badly — which it may, and
that is what it is for.

## Hard requirement

Compute capability **≥ 8.0**. `runpod-stage1.sh` checks this with `nvidia-smi`
before launching anything, because a run on a 7.5 card would produce numbers
that cannot mean what they claim. AMD is untested upstream and CPU is
unsupported (`docs/design/00-upstream-findings.md` §1.1).

## What stage 1 does and does not answer

It answers one question: **does batched inference on this model and this card
actually diverge?** Batch invariance is left OFF — `stage1_ladder()` fixes it
False for every cell — because the question is whether the *default* posture
diverges. Turning it on would answer a different question at twice the cost.

If divergence does not appear, that is the published result and stage 2 is
moot. This is why the expensive run sits behind a human decision point rather
than after an `&&`.
