---
id: "06b"
status: refuted
title: "REFUTED: q8_0 KV cache speeds up long-context decode"
measured: 2026-08-12
replaced_by: ["06a", "06c"]
---

# REFUTED: q8_0 KV cache speeds up long-context decode

**The refuted claim.** Decode slows with depth because the model must read a KV
cache that grows with every token. Therefore `--cache-type-k/v q8_0` halves those
bytes and is the single highest-leverage flag for long-context decode.

**What the measurement shows.** Halving the KV cache changed decode by **0% to 2%
at every depth**. It changed nothing.

| depth | f16 KV | q8_0 KV |
|---:|---:|---:|
| 0 | 63.34 t/s | 61.70 t/s |
| 16,384 | 41.86 | 41.43 |
| 65,536 | 20.21 | 20.65 |
| 131,072 | **12.13** | **12.12** |

Qwen3-Coder-30B-A3B Q8_0, three repetitions. If KV bandwidth dominated the
slowdown, halving the bytes should have roughly halved the decay. The decay did
not move at all.

## The mechanism the null result points to

The decay comes from attention **compute**, not from bytes. With flash attention
the model reads the KV in tiles and dequantises on the fly. `q8_0` therefore
halves the memory traffic and leaves the arithmetic identical. Unchanged timing
means the arithmetic is the binding constraint.

## What this changes

`--cache-type-k/v q8_0` buys **zero** decode speed and must never be recommended
for speed.

It remains a **memory-capacity** flag, and a valuable one. It is the difference
between a 1M context fitting on this box and not fitting. See
[10c](../verified/10c-llamacpp-can-quantize-the-v4-kv-cache.md).

## Why this is worth keeping

The refuted reasoning is correct-sounding and the flag is real. Someone who
reasons from KV growth to KV bandwidth will reach the same wrong conclusion, and
the flag will appear to work because it does help capacity.
