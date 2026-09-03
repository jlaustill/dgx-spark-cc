---
id: "11b"
status: verified
title: --cache-reuse is unavailable on DeepSeek V4
measured: 2026-08-13
see_also: ["11a", "16"]
---

# --cache-reuse is unavailable on DeepSeek V4

**Claim.** `llama_kv_cache_dsv4::get_can_shift()` returns false unconditionally,
at `llama-kv-cache-dsv4.cpp:1394`. Therefore `llama_memory_can_shift()` is false,
and the server silently zeroes `n_cache_reuse` at
`server-context.cpp:1278-1291`.

The flag has no effect on V4, and nothing reports that it was ignored.

## The tension worth naming

V4's compressed rows are the reason 512k of KV fits in 7 GiB. See
[06c](06c-kv-cost-per-token-by-architecture.md).

Those same compressed rows are the reason positions are block-derived and cannot
be shifted.

**The architectural feature that buys the context is the feature that blocks the
cache repair.**

## See also

A separate hardcoded `return 0` removes the checkpoint fallback that would have
covered part of this. See
[16](16-a-hardcoded-return-zero-costs-29000-tokens.md).
