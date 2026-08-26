---
id: "19"
status: unverified
title: Removing attention layers flattens decode decay, where quantizing the KV cache did not
measured: 2026-08-26
see_also: ["06a", "06b", "06c", "20"]
---

# Removing attention layers flattens decode decay, where quantizing the KV cache did not

**Claim.** Decode slows with depth because of attention *compute*, not KV *bytes*.
[06b](../refuted/06b-q8-0-kv-speeds-up-long-context-decode.md) established the
negative half of that: halving the bytes changed nothing. Qwen3-Coder-Next is the
positive half. It does not shrink the KV cache — it removes attention entirely
from 36 of 48 layers — and the decay collapses.

## What is measured

Qwen3-Coder-Next Q4_K_M, 262,144 context, `--parallel 1`. Medians parsed from
16 hours of production serving: 2,173 completed requests, 5.54 h of model time,
zero truncations.

| depth band | n | median decode | median prefill |
|---|---:|---:|---:|
| 0 – 4,096 | 20 | **65.4 t/s** | 1457 t/s |
| 4,096 – 16,384 | 90 | 60.1 | 1461 |
| 16,384 – 65,536 | 750 | 46.9 | 1152 |
| 65,536 – 131,072 | 941 | 37.1 | 790 |
| 131,072 – 200,000 | 334 | 29.6 | 618 |
| 200,000 – 300,000 | 38 | **24.9** | 243 |

Deepest context reached: **213,208 tokens**.

## The comparison

Against [06a](../verified/06a-shallow-decode-is-bandwidth-bound.md) and
[06b](../refuted/06b-q8-0-kv-speeds-up-long-context-decode.md), measured on this
same box:

| intervention | what it changes | decode decay |
|---|---|---|
| `--cache-type-k/v q8_0` on Qwen3-Coder-30B | KV **bytes**, halved | **0–2%. Nothing.** |
| Qwen3-Coder-Next's hybrid | attention **compute**, removed from 36 of 48 layers | **5.2× → 2.6×** |

The 30B fell 63.34 → 12.13 t/s by 131,072 — a factor of **5.2**. Qwen3-Coder-Next
falls 65.4 → 24.9 over a range **1.6× deeper**, a factor of **2.6**. At the one
depth band both cover, 65,536–131,072, it is 37.1 against 12.13: **3.1×**.

`full_attention_interval = 4`, so 12 of 48 layers are full attention and the other
36 are gated DeltaNet with a fixed-size recurrent state. A DeltaNet layer's
per-token work does not grow with depth. If the decay were bytes-bound, removing
three quarters of the *layers that have bytes* and leaving the rest untouched
would be a smaller effect than halving the bytes of all of them. It is far larger.

Shallow decode is nearly identical — 63.34 against 65.4 — despite 80B total
parameters against 30B, because both are ~3B active and Q4_K_M carries fewer bytes
per parameter than Q8_0. That is
[06a](../verified/06a-shallow-decode-is-bandwidth-bound.md) holding on a third
model.

## Why this is unverified

**It is not a single-variable experiment.** 06b was: same model, one flag. This is
a cross-model comparison, and three things move at once — architecture, quant
(Q4_K_M against Q8_0), and parameter count. The architecture is the only one with
a mechanism that predicts a *slope* change rather than an offset, which is why the
inference is worth making, but nothing here rules the others out by measurement.

**The two curves come from different instruments.** 06a is `llama-bench` at exact
depths, three repetitions. This is production medians over bands, with the depth
distribution set by whatever was being worked on. Band medians are not point
measurements.

**Prefill in the table is pessimistic.** This window ran with the default prompt
cache and was thrashing it, so some "fresh" prefill was re-reading context that
had already been read. See
[21](21-the-default-prompt-cache-is-too-small.md). Decode is unaffected — it is
measured per generated token, independent of how the context arrived.

## Completing test

Run `llama-bench` against Qwen3-Coder-Next at 06a's exact depths — 0, 16,384,
65,536, 131,072 — three repetitions, and put the two curves on one axis. That
removes the instrument difference. To separate architecture from quant, add a
Qwen3-Coder-30B Q4_K_M arm: if the decay tracks architecture the 30B stays at
~5×, and if it tracks quant it moves toward 2.6×.

Remember the noise floor is ~4%. See
[08b](../verified/08b-the-bench-noise-floor-is-4-percent.md).
