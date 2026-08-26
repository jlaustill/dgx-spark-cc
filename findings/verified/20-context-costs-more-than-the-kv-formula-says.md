---
id: "20"
status: verified
title: Context costs 38 percent more than the KV formula says
measured: 2026-08-26
see_also: ["06c", "12b", "19"]
---

# Context costs 38 percent more than the KV formula says

**Claim.** The KV-per-token formula in
[06c](06c-kv-cost-per-token-by-architecture.md) tabulates the KV cache. What you
must actually budget is the KV cache **plus** the graph and compute buffers that
scale with context. On Qwen3-Coder-Next that gap is 38%, and budgeting from the
formula alone understates the real cost by 2.3 GiB at full context.

## Evidence

Two loads of the same model, `--cache-ram 0` so the prompt cache cannot confound
the reading, resident memory taken after load with no requests served:

| | resident | model + context |
|---|---:|---:|
| baseline, no model | 4,053 MiB | — |
| `--ctx-size 65536` | 54,091 MiB | 50,038 MiB |
| `--ctx-size 262144` | 60,466 MiB | 56,413 MiB |

6,375 MiB over 196,608 tokens = **34,000 B/token = 33.2 KiB/token**.

The formula gives 24.0 KiB: 12 full-attention layers × 2 KV heads × 256 head_dim
× (K+V) × f16. The remaining **9.2 KiB/token is graph and compute buffer**, not
KV.

## Two independent checks

**Weights.** Extrapolating the line back to zero context gives 47,913 MiB of
weights, or 46.8 GiB. The GGUF reports 46.3 GiB. The line is anchored correctly at
both ends.

**A number predicted before it was looked up.** The server's prompt-cache eviction
log records the size of each evicted entry. The largest was 6,959 MiB. At the
formula's 24 KiB/token that implies a 297,000-token conversation, which is
impossible — the context is 262,144 and the deepest ever served was 213,208. At
the measured 33.2 KiB/token it implies **214,619 tokens**, against a deepest-seen
context of **213,208**. That is 0.7% apart, and it was an anomaly that the wrong
number could not explain and the right one resolved without adjustment.

## What this changes

Budget context at the measured rate, not the derived one. On this box
Qwen3-Coder-Next's full 262,144 context costs **8.3 GiB, not 6.0**.

The correction is not specific to this model. Every derived row in
[06c](06c-kv-cost-per-token-by-architecture.md) is a KV figure, and every one of
them will understate the memory a server actually needs by whatever its
context-scaling buffers cost. 06c already separates measured rows from calculated
ones and marks them in place; this says the calculated ones are biased low, in one
direction, by an amount nobody has characterised across architectures.

`qwen3next-server.sh` carries 34,000 as its f16 `PER_TOK`. Its q8_0 value of
21,712 halves only the KV half and leaves the buffer term alone; that one is an
estimate and is labelled as one in the script.

## Limits

**One model, two points.** A line through two measurements cannot show curvature.
If the buffer term is not linear in context, the 33.2 KiB figure is a chord across
64k–256k and not a slope, and it would misprice a much smaller or much larger
context.

`free` was read to the nearest MiB and drifted ~100 MiB between two readings of
the same state, which is ~1.5% of the 6,375 MiB delta. Well inside the ~4% noise
floor from [08b](08b-the-bench-noise-floor-is-4-percent.md), but not zero.

The 9.2 KiB is a residual, not an itemised allocation. It is named "graph and
compute buffer" because that is what scales with context in llama.cpp, and it was
not read out of an allocator.
