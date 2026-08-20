---
id: "10c"
status: verified
title: llama.cpp can quantize the V4 KV cache, and that is what makes 1M context fit
measured: 2026-08-11
see_also: ["06b", "06c", "10a"]
---

# llama.cpp can quantize the V4 KV cache, and that is what makes 1M context fit

**Claim.** llama.cpp implements `deepseek4` with the real compressed attention,
including `INDEXER_TOP_K`, `COMPRESS_RATIOS` and the sliding window. The cheap KV
therefore survives. Unlike `ds4-server`, llama.cpp can also quantize the KV
cache. That single capability is the difference between a 1M context fitting on
this box and not fitting.

This is the reason to prefer llama.cpp for V4, and it does not depend on the
contested performance rows in
[10a](../unverified/10a-llamacpp-beats-ds4-server-for-v4.md).

## Evidence

- `n_ctx_slot = 1048576`, with no capping.
- 106 of 121 GB resident under `mlock`.
- `/v1/messages` returns native `thinking` blocks.
- A generated SWAR `popcount64` compiled clean under `-Wall -Wextra` and matched
  `__builtin_popcountll` on all test cases.

## Throughput against depth

DeepSeek-V4-Flash UD-IQ3_XXS, 1M ctx, q8_0 KV:

| Prompt depth | Prefill | Decode |
|---:|---:|---:|
| ~0 (43 tok) | — | **16.30 t/s** |
| 116k (complete) | **210.5 t/s** | **12.44 t/s** |

Both curves decay with depth. Prefill attention is superlinear in context, and
decode must read a KV cache that grows with every token. See
[06a](06a-shallow-decode-is-bandwidth-bound.md).

## Limits

The shallow decode figure comes from one smoke test, and 276 of its 517 tokens
were `thinking` blocks. V4 Flash is a reasoning model, so a substantial and
variable fraction of every response is deliberation that the user never sees.
**n=1. Do not treat that ratio as a rate.**

Quantizing the KV cache buys capacity and not speed. See
[06b](../refuted/06b-q8-0-kv-speeds-up-long-context-decode.md).
