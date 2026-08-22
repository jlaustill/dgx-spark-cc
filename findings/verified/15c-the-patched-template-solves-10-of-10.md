---
id: "15c"
status: verified
title: The patched template solves 10 of 10 eval tasks against stock's 4 of 10
measured: 2026-08-18
see_also: ["15a", "15b"]
---

# The patched template solves 10 of 10 eval tasks against stock's 4 of 10

**Claim.** The in-place template is not merely faster. It solves every task in a
10-task agentic eval, including all six that stock failed, in 40% less
wall-clock.

## Method

Ten real closed issues, each with a known-good patch, scored fail-then-pass on
the project's own gate. The gate is transpile, match `.expected.*`, gcc,
cppcheck, clang-tidy and MISRA.

Claude Code drove this server and edited the repo with tools. This is the actual
workload, not a prompt comparison.

## Result

| | stock | patched |
|---|---:|---:|
| **solved** | **4/10** | **10/10** |
| prefill tokens | 15,341,796 | **1,877,020** (8.2x less) |
| prefill **per turn** | 34,789 | **2,005** (**17x less**) |
| turns | 441 | 936 |
| wall clock | 14.3 h | **8.6 h** |
| timed out (90 min cap) | **9/10** | 2/10 |

Prefill **per turn** is the cleanest figure here. It normalises for how much work
each arm did, so turn count does not confound it. Stock burns about 35k tokens of
redundant re-reading on every single turn.

The concern that inline reminders might be weighted differently and hurt
behaviour is not supported. The patched arm is better on every axis measured.

## Limits

**Stock's 4/10 is a lower bound.** Nine of its ten tasks hit the 90-minute cap,
so with unlimited time stock would solve more.

The supported claim is **"under a fixed time budget, patched solves 2.5x as
many"**. This finding does not claim that the template makes the model smarter.

Two cases resist even that reading. On issue #1094 stock spent 43 turns and
failed, where patched needed 34. On issue #1037 stock spent 50 turns where
patched needed 26. **n=2 is not a mechanism.**

One anomaly is unexplained. **Issue #1012** is the only task where stock was
cheaper, at 50 minutes with no timeout, while patched took the full 90 minutes
and burned 750k prefill, which is 4x its own average. Both arms solved it.
