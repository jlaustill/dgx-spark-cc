---
id: "03"
status: verified
title: The disk cache can evict the checkpoints that would have helped it
measured: 2026-08-13
supersedes: "A correction issued during verification, which read the configured step from source and concluded the spacing was 10,240. That correction was itself wrong and is retracted."
see_also: ["01a", "01b", "11a"]
---

# The disk cache can evict the checkpoints that would have helped it

**Claim.** Checkpoints are cumulative full prefixes. One long conversation writes
a ladder of them. That ladder can evict the checkpoints that would have prevented
the next full prefill.

## Evidence

```
18:45:12  kv cache evicted reason=disk-cache-full tokens=163840 hits=0
18:59:39  kv cache evicted reason=disk-cache-full tokens=307200 hits=0
```

The measured ladder for one 120,699-token conversation, taken by listing the
directory:

| file | bytes | ~ tokens | delta |
|---:|---:|---:|---:|
| 1 | 305,964,886 | 21,908 | 21,908 |
| 2 | 587,926,187 | 42,097 | 20,189 |
| 3 | 869,887,377 | 62,286 | 20,189 |
| 4 | 1,151,851,315 | 82,475 | 20,189 |
| 5 | 1,433,821,833 | 102,665 | 20,190 |
| 6 | 1,468,812,441 | 105,171 | 2,505 |

Six files hold 5.4 GiB.

- Cost is **13.64 KiB per token**, from the shutdown checkpoint. That is
  1,607.59 MiB divided by 120,699 tokens. The stated 13.5 KiB is correct.
- Checkpoint spacing is **20,189 tokens**. The stated ~20,480 is correct.
- Scaled to a 320k conversation, this gives about 16 files and about 38 GiB. File
  count grows linearly and total size grows quadratically. The original document
  stated about 21 files and about 46 GiB, which is the same order.

## The eviction policy

The score at `ds4_kvstore.c:532` is `(effective_hits + 1.0) x tokens/file_size`.
Hits decay on a 6-hour half-life.

Hit-weighting is real but weak. The term that kills intermediate rungs is
`kv_cache_incoming_supersedes_continued()`. It multiplies a superseded rung that
has never been hit by **0.05**.

That demotion is deliberate and correct for append-only growth, because a longer
prefix strictly dominates its ancestors. It is wrong for a diverging workload.
See [11a](11a-prefix-cache-payoff-is-bimodal.md) for the same theme.

## A retracted correction

An earlier verification pass read
`KV_CACHE_DEFAULT_CONTINUED_INTERVAL_TOKENS = 10000`, aligned it up to 2048, and
concluded that the interval was 10,240 rather than 20,480.

That is the **configured step**, not the spacing the server realises.
`ds4_kvstore_continued_store_target()` fires only when
`live_tokens % step == 0`, and prefill advances in batches that land on every
second multiple. The observed spacing is 20,189.

The original document was right and the code-derived correction was wrong.
Reading the constant is not the same as measuring the behaviour.

## Practical

The cache reached **225 GB** on disk in normal use. Budget for that. A 64 GiB
budget defeats itself.
