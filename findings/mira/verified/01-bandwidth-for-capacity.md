---
id: "01"
status: verified
title: An RTX 5070 Ti buys memory bandwidth and pays with capacity
measured: 2026-09-03
see_also: ["02", "04"]
---

# An RTX 5070 Ti buys memory bandwidth and pays with capacity

**Claim.** This box makes the opposite trade to the Spark, and every other
finding in this tree follows from it.

## The machine

| | |
|---|---|
| Host | `linux-Thelio-Mira`, ASUS board |
| GPU | NVIDIA GeForce RTX 5070 Ti (GB203), **16303 MiB**, cc **12.0**, ~896 GB/s |
| GPU link | PCIe 5.0 x16, negotiated at full width |
| CPU | Ryzen 9 7950X3D, 16C/32T, **128 MiB L3** |
| System RAM | 4x32 GB DDR5, 2 channels, **3600 MT/s configured** (5600 rated) |
| Storage | Crucial T705 4 TB, PCIe 5.0 |
| llama.cpp | pinned at `687e778`, built `-DCMAKE_CUDA_ARCHITECTURES=120a-real` |

Display runs on the AMD Raphael iGPU, so no VRAM is spent on a framebuffer.
llama.cpp reports **15839 MiB** usable.

## The inversion

| | spark (GB10) | mira (this box) |
|---|---:|---:|
| capacity | 121 GB unified | 16 GB VRAM + 124 GB system |
| bandwidth | ~273 GB/s for everything | ~896 GB/s VRAM, **~58 GB/s** system |
| the two pools | one | separate, across PCIe |

[spark/00](../../spark/verified/00-capacity-for-bandwidth.md) says of the Spark
that "there are no offload decisions." Here there is nothing else.

## Almost nothing fits

Computed against 15.2 GiB usable, using the KV rates measured in
[spark/06c](../../spark/verified/06c-kv-cost-per-token-by-architecture.md) and
corrected by [spark/20](../../spark/verified/20-context-costs-more-than-the-kv-formula-says.md):

| model / quant | weights | max context that fits |
|---|---:|---:|
| Qwen3-Coder-30B-A3B Q4_K_M | 18.6 GiB | weights alone exceed VRAM |
| Qwen3-Coder-30B-A3B IQ3_XXS | 12.2 GiB | ~42k |
| Qwen3-Next-80B-A3B any quant >= Q3 | >= 36 GiB | does not fit |
| **gpt-oss-20b MXFP4** | 11.27 GiB | **~168k** |

**Exactly one candidate model fits fully in VRAM at agentic context depth**, and
it is the one that
[spark/15e](../../spark/verified/15e-gpt-oss-drops-mid-conversation-system-messages.md)
disqualifies for agentic work: its template has no `system` branch, so
mid-conversation reminders are silently dropped.

## Limits

The DDR5 figure is 57.6 GB/s theoretical from 3600 MT/s x 8 B x 2 channels, not
a measured achieved bandwidth. Four DIMMs on AM5 is why it trains at 3600 rather
than its rated 5600; whether EXPO can recover any of that is untested.

Weight sizes are file sizes on disk. Every model listed as "does not fit" was
excluded by arithmetic, not by a load attempt.
