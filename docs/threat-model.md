# BARRIER — Threat Model

**Status:** draft · **Satisfies:** FR-B-01 · **Date:** 2026-08-30
**Reviewed against:** `docs/design/03-lld.md` §4.3, ADR-006, ADR-007

Written before the attack code, deliberately. A threat model produced after the
exploit tends to describe the exploit rather than the system.

---

## 1. The scenario

A bank runs one shared LLM inference platform. Two desks use it:

| Tenant | Desk | What they send |
|---|---|---|
| `tenant-a` | Equity Research | Company analysis, published research drafts |
| `tenant-b` | M&A Advisory | Live deal analysis — **material nonpublic information** |

An **information barrier** separates these desks. It is not a nice-to-have: it is
a regulatory obligation, it is audited, and the compliance department spent real
money constructing it. Research must not learn what M&A is working on.

Both desks call the same model, through the same gateway, served by the same pool
of pods. That is the whole point of a shared platform — and it is where the
barrier meets an assumption nobody wrote down.

---

## 2. What llm-d actually does

Confirmed from source at `llm-d-router` v0.10.0, not inferred from documentation
(`pkg/epp/framework/plugins/requestcontrol/dataproducer/prefixhash/hashing.go`):

```go
h := xxhash.New()
h.Write([]byte(request.TargetModel))              // model scoping
if cacheSalt := ...CacheSalt; cacheSalt != "" {   // OPTIONAL, client-supplied
    h.Write([]byte(cacheSalt))
}
```

The prefix block-hash chain is seeded with the **target model** and an **optional,
client-supplied `cache_salt`**. Nothing else. Not the tenant, not the API key, not
the namespace.

So by default, two tenants on the same model **share one prefix-cache namespace.**

### The primitive already exists

`cache_salt` is a real security control. vLLM added it for exactly this purpose,
llm-d honours it, and it is documented as isolating prefix caches in multi-tenant
environments. **BARRIER does not invent salting, and must never claim to.**

The gap is that it is **unenforced**: optional, client-supplied, and bound to
nothing.

---

## 3. Actors and trust boundaries

```
      tenant-a (attacker)          tenant-b (victim)
              │                            │
              └──────────┬─────────────────┘
                         ▼
        ┌────────────────────────────────┐
        │  PROXY  ← THE TRUST BOUNDARY   │  authenticates; issues identity
        └────────────────────────────────┘
                         ▼  ext-proc
        ┌────────────────────────────────┐
        │  EPP (Endpoint Picker)         │  prefix index — shared by default
        └────────────────────────────────┘
                         ▼
        ┌────────────────────────────────┐
        │  model server pool             │  vLLM's own KV cache
        └────────────────────────────────┘
```

**The proxy is the trust boundary.** Everything behind it trusts the identity the
proxy asserts, and trusts it *only* because the proxy strips whatever the client
sent (ADR-006). That stripping is not hardening around the mitigation — it is half
of the mitigation. Without it the identity header is attacker-controlled and the
plugin is deriving a salt from a value the attacker chose.

---

## 4. The attacker

**Capabilities.** An ordinary API caller. Valid `tenant-a` credentials, unlimited
requests within rate limits, full control of its own request bodies and headers,
and a clock.

**Observations.** Only what the API returns: status, headers, body, and timing.

**Explicitly NOT in the model.** Node or hypervisor access, ability to read the
EPP's memory or metrics endpoint, ability to run code on the model-server pods,
network position between proxy and EPP, or access to Kubernetes secrets. An
attacker with any of those has better paths than a cache side channel, and
defending against them is a different project.

**Goal.** Learn whether `tenant-b` recently submitted a prefix the attacker can
guess — for example `"Analyse the proposed acquisition of <TARGET> by <ACQUIRER>"`.
Confirming that guess is confirming MNPI, and it crosses the information barrier
without a single byte of `tenant-b`'s data ever being returned.

---

## 5. The three failure modes

`cache_salt` exists, so the vulnerability is not its absence. It is that all three
of these work against a stock deployment:

| # | Mode | How it works | Why the control does not stop it |
|---|---|---|---|
| **F1** | **Omission** | The attacker sends no `cache_salt` | The field is optional. No salt means the default namespace — which is where every other tenant who also omitted it lives. |
| **F2** | **Forgery** | The attacker sends the victim's salt | Nothing binds a salt to an identity. A salt learned from a config repo, a log, a shared runbook, or simply guessed is replayable by anyone. |
| **F3** | **Negligence** | The victim never sets a salt | The honest tenant is silently unprotected, and has no way to tell. Security that depends on every participant remembering is not a control; it is a hope. |

**F3 is the one that matters most in practice.** F1 and F2 need an attacker. F3
needs only a busy team shipping a feature.

---

## 6. The two channels

These are distinct vulnerabilities with different lifetimes, and conflating them
would overclaim.

### 6.1 The routing index — approximate path *(default)*

`approx-prefix-cache-producer` maintains an **in-EPP LRU index of the router's own
routing history**. It records what was routed where, not what is cached.

Consequence: it **leaks after the engine has evicted the blocks.** A prefix
submitted an hour ago and long since evicted from every pod's KV cache can still
be present in the EPP's memory of where it went. This is a longer-lived channel
than the classic timing side channel, and it is the one the published literature
does not describe.

### 6.2 The engine cache — precise path

`precise-prefix-cache-producer` reflects real KV-cache contents, streamed from
vLLM over ZeroMQ. This is the classic timing channel: a cache hit prefills far
faster than a cold miss, and TTFT is observable to any caller. Bounded by actual
eviction, so shorter-lived.

### 6.3 What is observable where

| Signal | Simulator | Real vLLM |
|---|---|---|
| TTFT hit vs miss | **No** — the simulator does not vary TTFT on cache hits (D-01, issue #347 closed as not-planned) | Yes |
| `x-gateway-destination-endpoint-served` | **No** — in `OutputInjectionHeaders`, stripped from responses (`handlers/response.go:202`) | No |
| Endpoint scores | **No** — `--emit-endpoint-scores` writes to Envoy dynamic metadata, not to the client | No |
| Anything else | **Open — this is spike S-02** | — |

llm-d's own hygiene here is good, and it is why S-02 is a real question rather
than a formality. If the answer is "nothing", FR-B-03 becomes an
operator-instrumented demonstration and the attacker-observable oracle moves to
real vLLM (LLD §7, decision rule fixed in advance).

---

## 7. The security property

**Claimed.** Under the hardened configuration, a request from tenant A can never
produce a prefix-cache hit on blocks contributed by tenant B, and no observation
available to an ordinary caller distinguishes "tenant B submitted this prefix"
from "tenant B did not".

**Mechanism.** The salt is derived, not accepted:

```
salt = HMAC-SHA256(server_secret, tenant_id)[:32]
```

Three obligations, each closing a specific failure mode:

| Obligation | Closes | Consequence if omitted |
|---|---|---|
| 1. Derive by HMAC from proxy-vouched identity; never read the client's value | F1, F2 | The attacker keeps choosing its own namespace |
| 2. Seed the EPP prefix hash chain with it | 6.1 | The routing index stays shared |
| 3. **Rewrite the outbound body's `cache_salt`** | 6.2 | The engine's real KV cache stays shared — the weaker half presented as the whole |

Plus `failClosed`: a request with absent or malformed identity is **rejected**, not
routed with an empty salt. An empty salt is the default namespace, so failing open
here would return the caller to precisely the exposure being fixed, while looking
like success.

**Preserved.** Cache locality *within* a tenant is untouched — the same tenant
derives the same salt on every request, so intra-tenant prefix hits work exactly
as before. That is what makes the cost bounded rather than catastrophic, and
FR-B-07 measures it rather than asserting it.

---

## 8. What this does not defend against

Stated plainly, because a threat model that claims too much is worse than none.

- **A co-tenant with node or hypervisor access.** Out of scope (§4).
- **Timing channels not mediated by the prefix cache** — queue depth, GPU
  contention, memory pressure. A busy pod is slower for everyone, and that is
  information, though far noisier and not prefix-specific.
- **A compromised salt secret.** Anyone holding it derives every tenant's salt,
  which restores F2 in full. Hence: minimum 32 bytes, never logged, never in
  values files, mounted from a Secret. Rotation invalidates warm cache — a real
  operational cost the writeup should name rather than skip.
- **A malicious or misconfigured proxy.** The entire guarantee is conditional on
  the proxy stripping client-supplied identity headers. This is the single
  assumption the whole mitigation rests on, and it is why ADR-006 puts it in the
  deliverable rather than the prose.
- **Content inference from model outputs.** Different problem entirely.
- **The precise path's residual**, whatever it proves to be. Obligation 3 should
  close it, since the salt reaches vLLM's own block hash (F-03) — but that is
  measured (FR-B-08), not assumed.

---

## 9. Prior art

**PrefixWall / CacheSolidarity — [arXiv 2603.10726](https://arxiv.org/abs/2603.10726).**
Demonstrates timing-based prompt reconstruction against shared vLLM automatic
prefix caching and proposes selective prefix isolation. Nine models, single A100,
**single-node vanilla vLLM**. No routing layer, no shipped plugin, and no
confidence intervals or p-values reported.

**DualMap — [arXiv 2602.06502](https://arxiv.org/abs/2602.06502).** Distributed LLM
serving using independent hash functions for cache affinity and load balancing.
The performance-motivated cousin of what BARRIER does for security, at the same
layer. Its existence strengthens the design — the hash structure is already
understood to be tunable; we tune it for isolation.

**What remains ours:** the routing-index channel (§6.1), which survives engine
eviction and which neither paper describes; a mitigation shipped as a registered
plugin rather than proposed; pre-registered statistics (NFR-05); and the
regulated-institution framing, where the prefixes themselves are the sensitive
material.

---

## 10. Responsible disclosure

**No claim of a vulnerability in llm-d.** `cache_salt` is a documented control that
works as designed. The finding is that it is **unenforced by default in a
multi-tenant deployment** — a configuration and threat-model gap in the default
posture, demonstrated against our own cluster (NFR-18).

If implementation surfaces something that looks like a genuine upstream
vulnerability, work **stops** and it goes to Roshan for responsible disclosure
before anything is published.
