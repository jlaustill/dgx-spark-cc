---
id: "05c"
status: refuted
title: "REFUTED: CLAUDE_SLOW_FIRST_BYTE_MS fixes prefill timeouts"
measured: 2026-08-16
replaced_by: ["05a", "05b"]
---

# REFUTED: CLAUDE_SLOW_FIRST_BYTE_MS fixes prefill timeouts

**The refuted claim.** Long prefills cross the client's timeout, and raising
`CLAUDE_SLOW_FIRST_BYTE_MS` extends the budget and prevents the abort.

**What the measurement shows.** The variable does nothing. Setting it changes the
budget in neither direction.

| config | budget |
|---|---:|
| *(default)* | 300.9 s |
| `CLAUDE_SLOW_FIRST_BYTE_MS=60000` | **300.9 s** |
| `CLAUDE_SLOW_FIRST_BYTE_MS=600000` | **300.8 s** |

Measured against a stub that never answers, with Claude Code 2.1.228.

## What replaced it

`API_TIMEOUT_MS` is the variable that has an effect, and it can only **shorten**
the budget. The default budget is about 301 s and not 1800 s. See
[05a](../verified/05a-the-client-first-byte-budget-is-301-seconds.md).

The production failure mode is probably an idle timeout rather than a first-byte
timeout. See
[05b](../unverified/05b-what-governs-the-production-timeout.md).

## Why this is worth keeping

The refuted setting is easy to find and looks like the right knob. Someone who
sets it will believe the problem is handled, and nothing will report that it was
ignored.
