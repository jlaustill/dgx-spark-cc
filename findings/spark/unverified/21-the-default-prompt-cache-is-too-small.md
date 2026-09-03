---
id: "21"
status: unverified
title: The default prompt cache is too small, and costs 31 percent of model time
measured: 2026-08-26
see_also: ["02a", "04a", "11a", "19", "22"]
---

# The default prompt cache is too small, and costs 31 percent of model time

**Claim.** `llama-server` defaults `--cache-ram` to 8192 MiB. On this box that
holds about four deep conversations. Running two interleaved sessions against a
single slot thrashes it, and the re-prefills that follow cost **1.73 h of 5.54 h
of model time — 31%**.

## What is measured

16 hours of production serving, 2,173 requests, parsed from the journal.

Prefix reuse is excellent almost all of the time. Fresh tokens as a percentage of
context, for turns deeper than 2k:

| | fresh % of context |
|---|---:|
| p50 | **0.50%** |
| p75 | 2.08% |
| p90 | 39.97% |
| p95 | 99.73% |

The distribution is not long-tailed, it is **bimodal** — the same shape as
[11a](../verified/11a-prefix-cache-payoff-is-bimodal.md). A turn either re-reads
almost nothing or re-reads almost everything.

**202 of 2,156 turns (9.4%) re-prefilled more than half their context, and 176 of
those were mid-session** — the previous turn was already at comparable depth, so
they are not cold starts. Those 202 turns cost **2.21 h of the 2.84 h total
prefill**: 78% of all prefill time went to 9.4% of turns.

## The mechanism

The journal logs 193 evictions:

```
srv alloc: - making room for prompt cache entry, removing oldest entry (size = 519.590 MiB)
```

193 evictions against 176 mid-session re-prefills. Median evicted entry 1,688
MiB; largest 6,959 MiB. At 33.2 KiB/token
([20](../verified/20-context-costs-more-than-the-kv-formula-says.md)) a
100k-token conversation is ~3.2 GiB of saved state, so an 8 GiB cache holds two
or three of them.

The depth sequence shows why they compete. Consecutive turns:

```
70,526 -> 26,995 -> 79,290 -> 59,194 (54% re-prefill) -> 79,707 -> 61,178 -> 81,391
```

Two conversations, one near 60k and one near 80k, alternating. With `--parallel 1`
there is one slot, so the slot's prefix belongs to whichever spoke last and the
other is served from the RAM cache — until the cache overflows and it is not
there. Most alternations cost 1–3%. The ones that miss cost everything.

**This supersedes the operating assumption that one session runs against this box
at a time.** That was true when [02a](../verified/02a-small-fast-model-alias-shares-one-slot.md)
was written. It is no longer how the box is used, and the single slot was sized
for the old assumption.

## The change applied

`--cache-ram 24576` in `qwen3next-server.sh`, against ~59 GiB free. 24 GiB holds
roughly a dozen typical entries or three of the largest.

## Why this is unverified

**The fix has not been measured.** It is applied and the server is healthy, and
that is all that is known. More cache RAM can only fix re-prefills caused by
*eviction*. Any of the 176 caused by genuine prefix divergence
([04a](../verified/04a-prefix-divergence-defeats-caching.md)) will survive it
untouched, and nothing here separates the two populations.

The 193-to-176 correlation is suggestive, not causal. The two counts were not
matched turn by turn.

## Completing test

The box rebooted after this was applied, so the eviction counter starts from zero
on the new configuration — the old and new populations cannot be confused. After a
day of comparable use:

```bash
sudo journalctl -u qwen3next-server --no-pager -o cat \
  | grep -c 'making room for prompt cache entry'
```

**Re-baseline first.** The server moved to `--ctx-size 524288` on 2026-08-26
(see [22](../verified/22-the-context-ceiling-was-the-server-not-the-model.md)),
which makes cache entries proportionally larger — a 516k conversation is ~16.6
GiB of saved state against a 24 GiB cache. The 9.4% figure below was measured at
262,144 and is not a like-for-like comparison any more.

Zero evictions, and a full-re-prefill rate that has dropped from 9.4%, closes it.
Zero evictions with the rate *unchanged* is the more interesting result: it would
mean the cost was divergence all along, and would move this whole finding under
[04a](../verified/04a-prefix-divergence-defeats-caching.md).
