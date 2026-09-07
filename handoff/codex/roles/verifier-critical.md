# Role: VERIFIER-CRITICAL

Run with `codex --profile verifier-critical`. Use **in addition to** `codex/roles/verifier.md`
— everything there applies. This file adds depth for the tasks where ordinary review is not
enough.

**Applies to:** T-009, T-010, T-011 (receipt schema, signing, verify CLI) · T-013, T-014,
T-015 (statistics and the pre-registered bar) · T-037, T-038, T-039 (the security plugin) ·
T-045 (statistical evaluation).

---

These are the tasks where a subtle error silently corrupts a published result or a security
claim — where the code runs, the tests pass, and the output is wrong. Spend the effort.

## Where the real risk lives

**Statistics (`common/stats`).** The AUC, bootstrap, and permutation implementations are the
project's headline claim. Check them against known reference values, not merely for absence
of exceptions. Verify specifically:

- Ties handled correctly in AUC
- The bootstrap resamples the right axis
- The permutation test is genuinely two-sided
- Every function takes an explicit `rng_seed`, and no global RNG is touched anywhere

A statistic wrong in the fourth decimal still invalidates the claim it supports.

**Pre-registered thresholds.** NFR-05 fixes the bar: attack succeeds at AUC ≥ 0.75 with
bootstrap 95% CI excluding 0.5 and permutation p < 0.01; mitigation succeeds when the CI
contains 0.5. These are module constants with a test asserting them. **If a threshold moved,
that is not a code change — it is the project marking its own homework. Automatic FAIL.**

Also check, at T-045: the git history must show the thresholds committed *before* the
results. If that ordering does not hold, the pre-registration is worthless.

**Cryptography and receipts.** Canonicalisation (JCS) must be recomputed from the parsed
document, never trusted from the file. Signature verification must fail closed. The test-key
refusal must actually refuse. Every row of the LLD §5 exit-code taxonomy needs a test
producing exactly that code — verify the tests themselves, not just that they have the right
names.

**The security plugin.** Three obligations, all contractual (LLD §4.3):

1. Salt derived by HMAC from tenant identity — **never read from the client**
2. EPP prefix hash chain seeded with it
3. **Outbound request body's `cache_salt` rewritten** to the derived value

Check specifically that a client-supplied `cache_salt` is **overridden** — not merged, not
appended, not preferred — and that `failClosed` genuinely rejects rather than routing with
an empty salt. Each of those, done wrong, produces a mitigation that appears to work and
does not. That failure mode is worse than no mitigation, because it would be published as
one.

## Adversarial reading

For each criterion, ask: *what input would make this pass the test and still be wrong?*
Say so explicitly when you find one. If you cannot construct such an input, say that too —
it is useful evidence, not filler.

Verdict: **PASS** or **FAIL** per criterion, with the concrete failure scenario for anything
you fail.
