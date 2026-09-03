---
id: "06c"
status: verified
title: Attention architecture decides maximum context far more than parameter count
measured: 2026-08-12
see_also: ["06a", "10c", "19", "20"]
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
| Qwen3-Coder-Next | 48, of which **12** are attention | 2 | 256/256 | **24.0 KiB** derived, **33.2 KiB** measured |
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

## The derived rows are biased low

Every calculated row above is a KV figure. What a server needs is KV **plus** the
graph and compute buffers that scale with context, and on Qwen3-Coder-Next that
second term is 9.2 KiB/token — 38% on top of the formula. See
[20](20-context-costs-more-than-the-kv-formula-says.md).

So the two limits on this table are not symmetric. The calculated rows are not
merely unmeasured, they are **understated**, in one direction, by an amount that
has not been characterised across architectures. Read them as lower bounds on the
memory a context will cost.

Qwen3-Coder-Next is also the second architecture here that the standard formula
does not describe, and it breaks it differently from V4. V4's `head_count_kv = 1`
makes the formula *over*-count, because MLA stores a compressed latent. Qwen3-Next
makes it *under*-count at the row level unless you already know that
`full_attention_interval = 4` means three quarters of the layers hold no KV at
all. Two exceptions out of five rows is a poor rate for a formula.
