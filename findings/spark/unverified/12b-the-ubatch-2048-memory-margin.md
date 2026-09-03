---
id: "12b"
status: unverified
title: The ubatch 2048 memory margin survives a worst-case request
measured: 2026-08-12
see_also: ["12a"]
---

# The ubatch 2048 memory margin survives a worst-case request

**Claim.** `--ubatch-size 2048` costs about 6 GB of compute buffer, and the
remaining margin is enough for a worst-case request.

## What is measured

At 1M context the V4 server went from 106 GB resident to **112 of 121 GB**. It
loads and it runs.

## Why this is unverified

The margin is thin, and no worst-case request has been tested against it. The
flag is "free" only if that margin holds.

Set `DS_UBATCH=512` to revert if a future config runs out of memory on load.

## What does not depend on this claim

The prefill gain itself is verified and reproduced in production. See
[12a](../verified/12a-ubatch-2048-buys-19-to-31-percent-of-prefill.md).

## Completing test

Drive the 1M-context server at `ub 2048` with a maximum-length request and a full
KV cache. Record peak resident memory.
