---
id: "11a"
status: verified
title: Prefix caching assumes append-only growth, and coding agents are not append-only
measured: 2026-08-13
see_also: ["04a", "11b", "15a"]
---

# Prefix caching assumes append-only growth, and coding agents are not append-only

**Claim.** Two different things are called "the KV cache". Only one of them is a
questionable fit for this workload.

**Within a generation**, the KV cache is load-bearing and not optional. Without
it, producing token N re-derives K and V for all N-1 predecessors at every step.

**Across requests**, prefix caching bets on **append-only** growth. That is the
ChatGPT shape. A coding agent is not that shape. It front-loads a large context
and then rewrites it at structurally meaningful moments: plan mode moves to
execution, a subagent spawns and returns, compaction runs, tool results are
trimmed.

## Evidence

The payoff is bimodal and not average. This is verified on two independent
sessions. Reuse fraction across 31 tasks:

```
   0-  9%  #########  9
  10- 19%  #  1
  20- 29%  .  0
     ...            (nothing in the middle)
  80- 89%  #  1
  90- 99%  ###################  19
```

Prefix caching is worth roughly **9x while the prefix holds, and exactly nothing
across a break.**

## What this means

Whether prefix caching "makes sense" depends entirely on divergence frequency.
Divergence frequency is a property of the **client**, not of the server. See
[15a](15a-a-trailing-system-message-rewrites-the-head.md) for the client
behaviour that caused most of the breaks measured here.
