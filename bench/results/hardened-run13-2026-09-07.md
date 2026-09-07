> **CORRECTED BY RUN #14. The claim below that identity injection reached the
> plugin is WRONG**, and the correction is at the bottom of this file. Left
> standing rather than edited away, because a repository about verifiable claims
> does not get to quietly fix the one it got wrong.

# Run #13 — the hardened profile runs, and what that does and does not show

**Date:** 2026-09-07 · **Repo SHA:** `595a84f` · **Run:** BARRIER cluster #13,
4m 26s, both matrix jobs green · **First execution of `values-hardened.yaml`
against a live cluster.**

For twelve runs only the `default` profile had ever been executed. The mitigation
was tested code that had never met the thing it mitigates.

## What is now established

| | evidence |
|---|---|
| The hardened topology starts | `S-02 spike (hardened)` succeeded in 3m 47s |
| The proxy refuses unauthenticated callers | `gateway answered: 401` on a bare `GET /` |
| Tenant keys authenticate | 404 probes served, median latency 224.6 ms — an unmatched route would have been 401 at ~1 ms |
| ~~Identity injection reaches the plugin~~ | ~~404 served probes means the header the plugin read was put there by the proxy~~ — **false, see the correction below** |
| Keys stayed out of the evidence | `rendered.yaml` for the hardened profile carries `__KEY_TENANT_A__` placeholders, not credentials |

~~That last chain is the one worth reading twice.~~ The reasoning was sound and
the premise was not: the S-02 client **sends `x-llmd-tenant` itself**, so the
plugin was satisfied whether or not the proxy injected anything. See the
correction.

## What this does NOT show, and the aggregate that proves it

The obvious thing to reach for is the prefix index, and it says almost nothing:

| profile | run | hit-ratio sum / count | mean | index size |
|---|---|---|---|---|
| default | #12 | 400 / 404 | 0.990 | 8 |
| hardened | #13 | 399.5 / 404 | 0.989 | 9 |

Essentially identical, and **that is the expected result, not a null one.**

The S-02 probe schedule is dominated by tenant A repeating its *own* prefix 200
times. Same tenant means same derived salt, so those requests hit their own
earlier entries under both profiles — the mitigation is not supposed to change
them, and it does not. Exactly **one** probe in the whole run is a genuine
cross-tenant test: tenant B plants `secret_prefix + "victim"`, and tenant A's
first probe looks for it. One observation, drowned in 403 others.

So an aggregate hit ratio cannot measure this mitigation, and quoting the 0.990
against 0.989 either way would be meaningless. The index size moving 8 → 9 is
consistent with the salt creating a second namespace entry, and is also n=1.

## What FR-B-03 therefore needs

ADR-011 rescoped FR-B-03 to an operator-instrumented demonstration. Run #13
makes its shape concrete. It must isolate the single cross-tenant event that the
S-02 schedule buries:

1. Tenant B submits a distinctive prefix. Record the index state.
2. Tenant A submits the *same* prefix, once, on a cold client.
3. Read the match ratio **attributed to that request**, not to the run.
4. Repeat enough times, alternating fresh prefixes, to get an n worth a
   confidence interval — and run the identical schedule under both profiles.

The claim is then a difference in measured match ratio between two profiles on
the same schedule, which is the two-profile diff the project has promised since
the requirements were written and has never produced.

The pre-registered rule in `common/stats/decision.py` already applies: the attack
succeeds if the default profile clears the bar, and the mitigation succeeds if
the hardened profile's interval straddles chance. Both halves are needed, and
neither exists yet.

## Cost

Two GitHub-hosted runners, 4m 26s wall clock. £0.


---

# Correction — run #14, and F-27

**The claim that identity injection worked was wrong.** Run #14's FR-B-03
demonstration, which deliberately sends *no* identity header, got:

```
FR-B-03 FAILED: gateway answered 500 for a tenant request
epp: "tenant-salt: no authenticated tenant identity"
```

The proxy authenticated the caller — a 500 from the EPP, not a 401 from Envoy —
and then the plugin found no identity to salt with. So the injection was never
reaching it.

**Why.** Route-level `request_headers_to_add` and `request_headers_to_remove` are
applied by Envoy's **router filter**, which sits at the *end* of the HTTP filter
chain. `ext_proc` sits before it. So the EPP was reading the request as the
client sent it, and every route-level mutation was invisible to the thing the
mutation exists to protect.

**Why run #13 hid it.** The S-02 spike sets `x-llmd-tenant` on its own requests.
The plugin saw an identity on every probe and was satisfied — with the
*client-supplied* value. That is precisely the forgery vector ADR-006 exists to
close, running inside a profile labelled `hardened`, while the run reported a
passing trust boundary.

**The fix.** `envoy.filters.http.header_mutation` as a real HTTP filter placed
**before** `ext_proc`, carrying the remove-and-overwrite as per-route config. A
filter's per-route mutations run at that filter's position in the chain, so what
ext_proc reads is what the proxy vouches for.

**What this says about the method.** Run #13's error was not a wrong number — it
was a correct observation and an unwarranted inference from it. The observation
(404 probes served) was true. The inference (therefore the proxy injected the
header) skipped the possibility that something else supplied it. What caught it
was building an instrument that deliberately withholds the thing under test:
FR-B-03 sends no identity header, so nothing but the proxy could have provided
one.

Fourth guard in this project to contain the defect it was written to catch — and
the first where the guard was a *writeup* rather than code.
