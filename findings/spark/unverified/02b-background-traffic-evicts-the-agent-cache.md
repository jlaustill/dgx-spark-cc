---
id: "02b"
status: unverified
title: Background traffic evicts the agent's cache
measured: 2026-08-10
see_also: ["02a"]
---

# Background traffic evicts the agent's cache

**Claim.** Claude Code's background title and summary calls preempt the agent
loop on the same engine, and this evicts the agent's cache.

## Evidence

Three adjacent log lines show the two workloads alternating.

## Why this is unverified

The evidence is one observation of alternation. The test against the null
hypothesis has not run. The null hypothesis is that the observed alternation was
the agent's own divergence and not background traffic.

The alias half of this finding **is** verified. See
[02a](../verified/02a-small-fast-model-alias-shares-one-slot.md). The recommended
fix follows from the alias alone, so acting on it does not depend on this claim.

## Completing test

Run one agentic session with `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` and one
without it. Compare the reuse fraction per task between the two arms.
