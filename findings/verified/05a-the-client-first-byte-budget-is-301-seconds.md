---
id: "05a"
status: verified
title: The client first-byte budget is about 301 seconds and cannot be raised
measured: 2026-08-16
supersedes: "The original claim that the budget defaults to 1800 s."
see_also: ["05b"]
---

# The client first-byte budget is about 301 seconds and cannot be raised

**Claim.** Prefill grows with the conversation until it crosses the client's
first-byte budget. The failure mode is not a lost turn. Each retry sends the same
prompt and prefills it again.

## Evidence

Measured against a stub that never answers, with Claude Code 2.1.228:

| config | budget |
|---|---:|
| *(default)* | **300.9 s** |
| `CLAUDE_SLOW_FIRST_BYTE_MS=60000` | 300.9 s — **no effect** |
| `CLAUDE_SLOW_FIRST_BYTE_MS=600000` | 300.8 s — **no effect** |
| `API_TIMEOUT_MS=60000` | **60.5 s** — works |
| `API_TIMEOUT_MS=900000` | 301.0 s — cannot raise |

- The budget defaults to about **301 s**, not 1800 s.
- `API_TIMEOUT_MS` behaves as `min(value, ~300 s)`. It shortens the budget and
  never lengthens it.
- The client makes exactly **10 retries**, which is 11 POSTs. Each POST is
  byte-identical. The client then reports `Request timed out`.
- Backoff is additive and small, from 300.9 s to 335.1 s. It is not exponential.
  One request costs **58 minutes of repeated work**.

## Limits

The stub never sends a byte. `llama-server` does send bytes. The case study
contains prefills of **812.7 s that completed successfully**, so a hard 301 s
first-byte cap is not the production failure mode. See
[05b](../unverified/05b-what-governs-the-production-timeout.md).

`CLAUDE_SLOW_FIRST_BYTE_MS` does nothing in either direction. See
[05c](../refuted/05c-slow-first-byte-ms-fixes-prefill-timeouts.md).
