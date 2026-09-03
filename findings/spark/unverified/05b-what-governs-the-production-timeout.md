---
id: "05b"
status: unverified
title: An idle timeout, not the first-byte budget, governs production
measured: 2026-08-16
see_also: ["05a"]
---

# An idle timeout, not the first-byte budget, governs production

**Claim.** `server-task.cpp:1360` emits `message_start` when the server accepts
the task, and not when generation begins. The client therefore receives a byte
early, and the **idle** timeout becomes the binding one rather than the
first-byte budget.

This is the likely explanation for a contradiction:
[05a](../verified/05a-the-client-first-byte-budget-is-301-seconds.md) measures a
hard 301 s first-byte budget against a stub, but the case study contains prefills
of 812.7 s that completed.

## Why this is unverified

The mechanism is read from source and inferred. No measurement has confirmed it.

## What does not depend on this claim

Whatever governs the production timeout, it is demonstrably not
`CLAUDE_SLOW_FIRST_BYTE_MS`. That variable had no effect in either direction. The
recommendation stands regardless of how this question resolves.

## Completing test

Time the first SSE byte on one streaming request. Use a prompt of about 140k
tokens against a cold cache.
