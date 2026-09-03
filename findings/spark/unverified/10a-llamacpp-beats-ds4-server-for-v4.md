---
id: "10a"
status: unverified
title: llama.cpp beats ds4-server for DeepSeek V4
measured: 2026-08-11
see_also: ["10b", "10c"]
---

# llama.cpp beats ds4-server for DeepSeek V4

**Claim.** llama.cpp runs DeepSeek V4 better than the purpose-built `ds4-server`.

| | ds4-server | llama.cpp |
|---|---:|---:|
| Quant | q2 (~2.3 bpw) | **UD-IQ3_XXS (~3.06 bpw)** |
| Context | 512k (1M refused) | **1M** |
| Weights | 80.8 GiB | 95.9 GiB |
| KV | 7.1 GiB (f16 only) | **7.2 GiB @ 1M (q8_0)** |
| Total RAM | ~92 GiB @512k | **~106 GiB @1M** |
| Decode | 13.5 t/s | **16.3 t/s** |
| Prefill | 335 t/s | 300 t/s |

## Why this is unverified

**Quant, KV type and context all differ, so this is not a controlled
comparison.** A larger model that decodes faster is surprising and deserves
re-measurement at matched settings.

The prefill row is also suspect. `335 t/s` appears here as ds4-server's prefill
and also appears in
[08a](../verified/08a-there-is-no-universal-prefill-ceiling.md) as llama.cpp's V4
`pp4096 @ ub512`. One attribution may be transposed.

A separate controlled measurement suggests the transposition is **not** the
explanation, and that ds4-server does prefill faster. See
[10b](../verified/10b-ds4-server-prefills-faster-than-llamacpp.md).

## What does not depend on this claim

llama.cpp can quantize V4's KV cache and `ds4-server` cannot. That capability is
reason enough to prefer llama.cpp regardless of how the contested rows resolve.
See [10c](../verified/10c-llamacpp-can-quantize-the-v4-kv-cache.md).

## Completing test

Re-measure both engines at matched quant, matched KV type and matched context.
