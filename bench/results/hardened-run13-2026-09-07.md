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
| Identity injection reaches the plugin | `tenant-salt` runs `failClosed: true`; a request arriving without a vouched identity is **rejected**. 404 served probes means the header the plugin read was present, and it was put there by the proxy |
| Keys stayed out of the evidence | `rendered.yaml` for the hardened profile carries `__KEY_TENANT_A__` placeholders, not credentials |

That last chain is the one worth reading twice. `failClosed` turns the plugin
into its own assertion: if `OVERWRITE_IF_EXISTS_OR_ADD` had not fired, or had
fired on the wrong header name, every probe would have failed. **404 successful
probes is a passing test of the trust boundary**, not merely an absence of
errors.

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
