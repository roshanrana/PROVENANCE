# S-03 — Does any SGLang wire field reach the radix cache's namespace key?

**Status:** COMPLETE · **Date:** 2026-09-07 · **Verdict: AFFIRMATIVE**
**Method:** source read against `sgl-project/sglang` @ `30705c0`, cloned and grepped locally.
**Decision rule, fixed before reading** (mirrors S-02's discipline):

> The spike succeeds if a client-settable HTTP field is shown to reach the
> structure that namespaces the prefix cache, by an unbroken chain of source
> references. Absence of such a field is an equally valid, publishable verdict:
> it would mean obligation 3 cannot be met on SGLang and the mitigation must be
> published as engine-scoped.

---

## Verdict

**SGLang accepts `cache_salt` — the same wire field name as vLLM — and it
namespaces both the in-process radix tree and the KV-event hashes SGLang
publishes to llm-d.**

Obligation 3 (partition the engine's own cache) is therefore **met on SGLang by
the existing mitigation, unchanged**. No new plugin code is required, and the
BARRIER claim extends to SGLang-backed pools — subject to §4.

This is a stronger result than the amendment anticipated. A-04 as scoped
("extend `ApplySalt` to whatever SGLang uses") is **not needed**; what replaces
it is a smaller, sharper piece of work described in §4.

---

## 1. The chain, end to end

Every link verified in source. File paths are relative to the SGLang repo.

| # | Where | What |
|---|---|---|
| 1 | `srt/entrypoints/openai/protocol.py:398`, `:956`, `:1651` | `cache_salt: Optional[...]` on the completions, chat-completions and responses request models — "Cache salt for request caching" |
| 2 | `srt/managers/io_struct.py:352` | `GenerateReqInput.cache_salt` — the native `/generate` endpoint. Comment: *"Cache namespace used to isolate otherwise-identical prefixes."* |
| 3 | `srt/entrypoints/openai/serving_completions.py:135`, `serving_chat.py:1179` | the OpenAI layer forwards `cache_salt=request.cache_salt` into `GenerateReqInput` |
| 4 | `srt/managers/tokenizer_manager.py:1419` | forwarded into the scheduler request |
| 5 | `srt/managers/schedule_batch.py:974`, `:1050` | `Req.cache_salt = cache_salt or None` |
| 6 | `srt/mem_cache/radix_cache.py:508`, `:552` | `RadixKey(token_ids, req.extra_key, cache_salt=req.cache_salt)` |
| 7 | `srt/mem_cache/radix_cache.py:248-250` | `child_key()` returns `((extra_key, cache_salt), plain)` when a salt is present — entries with different salts are structurally disjoint |
| 8 | `srt/mem_cache/radix_cache.py:175-179` | `RadixKey` operations **raise** on mismatched `cache_salt`, so the isolation cannot be defeated by a merge |

Validation is real, not decorative: `io_struct.py:531-537` rejects a
non-string `cache_salt`, and an empty string is normalised to `None` rather
than being treated as a distinct namespace — so `cache_salt: ""` does not create
a third namespace that a careless mitigation might land tenants in.

## 2. The part that decides BARRIER's routing claim

`srt/mem_cache/utils.py:146-190`, `compute_node_event_hash_values` — the hashes
SGLang **publishes as KV events**, which are what llm-d's precise
prefix-cache index is built from:

```python
cache_salt = node.key.cache_salt
if cache_salt is None:
    return compute_node_hash_values(node, page_size)  # unsalted, shared
...
parent_hash = hashlib.sha256(b"sglang-cache-salt-v1\0" + cache_salt.encode("utf-8")).hexdigest()
```

The salt seeds the hash chain with an explicit domain separator, exactly as our
own `DeriveSalt` does. Consequences, in order of importance to BARRIER:

1. **A salted request produces salted KV-event hashes.** llm-d's precise
   prefix-cache index is partitioned by tenant on an SGLang pool, without any
   change to llm-d or to our plugin.
2. **`extra_key` is not enough.** It namespaces the in-process tree
   (`child_key`) but is **not** folded into the event hash — `get_hash_str`
   receives only the key's tokens and the parent digest. A mitigation built on
   `extra_key` would close the engine's own cache while leaving the
   routing-derived index shared. `cache_salt` is the field that closes both.
   This is a real trap: `extra_key` is the field SGLang's prefix-caching
   documentation shows for multi-tenancy, and it is the wrong one for this
   threat.
3. **The unsalted path is the shared namespace.** `cache_salt is None` falls
   through to `compute_node_hash_values`. This is the same unenforced-control
   gap BARRIER identifies in vLLM/llm-d, present in a second independent engine
   — which makes the finding a pattern rather than a quirk, and strengthens the
   write-up's central framing.

## 3. What this changes upstream of us

Nothing. `cache_salt` is llm-d's own field name, `ApplySalt` already writes it on
every body variant `tokenizer.CacheSaltFromBody` reads — including
`body.Generate`, whose omission was fixed in `ec00137` and which is precisely
the shape a tokenizing front-end drives an SGLang pool through. The salt reaches
an SGLang engine by the same path it reaches a vLLM one.

## 4. What is *not* established, and must not be claimed

Stated explicitly, because the temptation after a clean result is to overclaim.

- **This is a source read, not a live test.** No SGLang engine has been run, no
  request has been sent, no cache hit has been observed. The chain is
  unambiguous in source, but "verified by reading" and "verified by measuring"
  are different claims and the write-up must use the first one until A-03 runs.
- **Version-pinned.** Verified at commit `30705c0`. llm-d's own SGLang manifest
  pins `lmsysorg/sglang:v0.5.12`; whether that release carries the same chain is
  unverified, and the deployment must pin a version this was checked against.
- **The `extra_key` / `cache_salt` split is a documentation gap, not a defect.**
  Reporting it that way would be wrong.

**Replacement for A-04** (was: "extend the mitigation to SGLang's field"):
a test asserting that the derived salt survives to the engine as `cache_salt`
on the pre-tokenized path, and a paragraph in `docs/threat-model.md` recording
the `extra_key` trap and the unsalted-default finding. Roughly two hours, no
cluster. The mitigation code itself needs no change.
