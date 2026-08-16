# V5 — the client's timeout, and which knob actually moves it

**Date:** 2026-08-12 · **Verdict: REVISED. The recommended variable does nothing.**

## What #5 says

> Set `CLAUDE_SLOW_FIRST_BYTE_MS` / `CLAUDE_STREAM_IDLE_TIMEOUT_MS` well above
> worst-case prefill, and treat a timeout here as a correctness bug, not a hiccup.

with a table showing a **1800 s** budget.

## Method

A stub that accepts `/v1/messages` and never sends a byte. Claude Code 2.1.228 posts,
waits, gives up, and retries — the interval between POSTs *is* the budget, measured
exactly in one trial rather than bisected. Five configurations, each a fresh isolated
client (`CLAUDE_CONFIG_DIR` per probe).

## Result

| probe | config | first POST | retry | **budget** |
|---|---|---:|---:|---:|
| A | *(default)* | 18.9 s | 319.8 s | **300.9 s** |
| B | `CLAUDE_SLOW_FIRST_BYTE_MS=60000` | 3.4 s | 304.3 s | **300.9 s** |
| D | `CLAUDE_SLOW_FIRST_BYTE_MS=600000` | 3.5 s | 304.3 s | **300.8 s** |
| C | `API_TIMEOUT_MS=60000` | 3.4 s | 63.9 s | **60.5 s** |
| E | `API_TIMEOUT_MS=900000` | 3.3 s | 304.3 s | **301.0 s** |

Three conclusions, all falsifiable and all falsified against the document:

1. **`CLAUDE_SLOW_FIRST_BYTE_MS` does not control this abort.** Not at 60 s, not at
   600 s. The budget is 300.9 s either way — indistinguishable from default. The
   document's primary recommendation has no effect on the thing it is recommended for.
2. **`API_TIMEOUT_MS` does control it — downward only.** 60 s lowers the budget to
   60.5 s; 900 s leaves it at 301 s. It behaves as `min(API_TIMEOUT_MS, ~300 s)`.
3. **Retries carry a byte-identical body** (`b9400605e64c` across every one of probe A's
   attempts). The expensive half of #5 — each retry re-sends the same prompt — is
   ✅ **CONFIRMED**.

**Probe A ran to completion: 11 POSTs — one initial attempt plus exactly 10 retries —
then `Request timed out`.** The document's retry count is exactly right. Intervals drift
mildly with attempt number (300.9, 301.5, 302.5, 304.7, 309.3, 318.5, 339.0, 336.3,
334.8, 335.1 s), so there is backoff, but it is additive and small, not exponential.
Total elapsed before giving up: **58 minutes**. On a real server every one of those 11
attempts triggers a full prefill, which is precisely the "one timeout becomes hours of
thrash" the document warns about — ✅ **CONFIRMED**.

## The honest limitation, and what it implies

**This stub never sends a byte. `llama-server` does.** So the ~301 s measured here is
the *no-bytes-at-all* budget, and that is almost certainly not the production failure
mode — the case study contains prefills of **812.7 s that completed successfully**, and
#5's own table shows 1747.5 s and 1791.5 s prefills that returned. A hard 301 s
first-byte cap is incompatible with both.

The likely resolution: `server-task.cpp:1360` emits a `message_start` SSE event, and if
that goes out when the task is accepted rather than when generation begins, the first
byte arrives immediately and the binding constraint becomes the *idle* timeout — which
is plausibly where the document's 1800 s comes from.

**That does not rescue the recommendation.** Whatever governs the production case, it is
demonstrably not `CLAUDE_SLOW_FIRST_BYTE_MS`, which moved nothing in either direction.

**Completing test:** send one streaming `/v1/messages` with a ~140k prompt at a cold
cache and record the wall-clock arrival of the first SSE byte against prefill completion.
If the first byte precedes prefill, #5 should be rewritten around the idle timeout; if it
follows, then a ~301 s ceiling exists that no variable raises, and every cold start on
this box is unreachable out of the box.

## Reproduce

```
SS_PORT=8020 ./tools/stub-server.py
ANTHROPIC_BASE_URL=http://127.0.0.1:8020 ANTHROPIC_API_KEY=x \
  API_TIMEOUT_MS=60000 CLAUDE_CONFIG_DIR=/tmp/probe claude -p 'say hi'
```

Artifacts: `V5-stub.log`, `V5b-stub.log` … `V5e-stub.log`, `tools/stub-server.py`
