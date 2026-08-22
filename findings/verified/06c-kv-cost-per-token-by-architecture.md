---
id: "06c"
status: verified
title: Attention architecture decides maximum context far more than parameter count
measured: 2026-08-12
see_also: ["06a", "10c"]
---

# Attention architecture decides maximum context far more than parameter count

**Claim.** On a fixed memory budget, the attention architecture sets your maximum
context. Parameter count matters much less.

## Evidence

Read from GGUF metadata, except where the table says otherwise:

| Model | Layers | KV heads | k/v len | KV/token f16 |
|---|---:|---:|---:|---:|
| Qwen3-Coder-30B | 48 | 4 | 128/128 | **96.0 KiB** |
| gpt-oss-120b | 36 | 8 | 64/64 | 72.0 KiB full, **~36 KiB** effective (half the layers slide, window 128) |
| DeepSeek V4 Flash | 43 | **1** | **512/512** | formula gives 86 KiB, **which does not apply** |
| GLM-4.5-Air | 46 | 8 | 128 | ~184 KiB *(unverified, model not on disk)* |
| Qwen3-235B-A22B | 94 | 4 | 128 | ~188 KiB *(unverified, model not on disk)* |

## V4's 13.5 KiB per token is measured, not derived

V4's metadata reports `head_count_kv = 1` with `key_length = 512`. That is MLA.
The cache stores a compressed latent rather than per-head K and V, and the
sparse-attention ratio reduces it further.

The standard formula `2 x layers x heads x dim x 2` gives 86 KiB and is simply
the wrong formula for this architecture.

The 13.5 KiB figure comes from measurement. `ds4-server` held 7.08 GiB at 512k,
which is 14.2 KiB per token. Cite it as a measurement.

## Limits

Two rows in the table are calculated from published configuration and not read
from a file on this box. They are marked in place.

This architectural difference is what makes V4's 1M context possible at all.
