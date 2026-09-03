---
id: "04"
status: verified
title: The Spark beats this box on both halves of a turn for Qwen3-Next-80B
measured: 2026-09-03
see_also: ["01", "02", "03"]
---

# The Spark beats this box on both halves of a turn for Qwen3-Next-80B

**Claim.** On the same model, same commit and same instrument, the Spark is
1.08x faster on prefill and 1.50x faster on decode. There is no crossover, so
no prefill:decode mix makes this box the better choice for this model.

## Method

Both boxes run **the same file** — `Qwen3-Next-80B-A3B-Thinking-UD-Q6_K_XL`,
63.81 GiB, SHA256-verified — on llama.cpp `687e778`.

Measured through **one instrument**: `llama-server`'s HTTP `timings`, with a
byte-identical request body. Not `llama-bench` on one box and the server on the
other;
[spark/08b](../../spark/verified/08b-the-bench-noise-floor-is-4-percent.md) is
explicit that llama-bench transfers as a claim but not as precision.

Matched server flags, taken from `server-scripts/qwen3next-server.sh`:
`-c 262144 -ub 2048 -ctk f16 -ctv f16 --load-mode mlock`, `cache_prompt: false`.

Prompt is 29,701 tokens of real TypeScript. Synthetic text was tried first and
rejected — see [03](03-repetitive-prompts-inflate-offloaded-moe-prefill.md).

## Result

| | prefill @ 29.7k | decode |
|---|---:|---:|
| **spark** (GB10, 121 GB unified) | **1,325.9 t/s** | **41.47 t/s** |
| **mira** (5070 Ti, `-ncmoe 46`) | 1,225.6 t/s | 27.65 t/s |
| spark advantage | **1.08x** | **1.50x** |

Mean of 3 reps each; spreads 0.45% and 1.5%.

The split is the one
[01](01-bandwidth-for-capacity.md) predicts in direction, and the surprise is
its size. Prefill is compute-bound, and this box has far more FLOPs, yet it
still **loses** prefill — because at 262144 context only 2 of 48 expert layers
fit on the GPU, so prefill is reading experts across DDR5 too.

## Why -ncmoe 46 and not lower

At 262144 context, `-ncmoe 45` aborts with `CUDA error: out of memory`. KV plus
context-scaling buffers cost ~8.3 GiB at this depth
([spark/20](../../spark/verified/20-context-costs-more-than-the-kv-formula-says.md)),
which leaves room for only two layers of experts. 46 is the best this box can do
at the Spark's context size, not a tuning choice. See
[02](../unverified/02-moe-offload-is-linear-with-no-knee.md).

## Limits

**One model, one depth, one session.** Nothing here generalises to a model that
fits entirely in 16 GB — for those, this box has never been compared at all, and
[01](01-bandwidth-for-capacity.md) says gpt-oss-20b is the only such candidate.

**Decode was measured over 32 generated tokens.** Long generations may differ.

Both boxes were otherwise idle, but neither ran a repeated-launch protocol
across sessions, so these carry within-session error bars only.

**This is a throughput result, not a quality result.** It says nothing about
which box solves more tasks; that needs the eval in `tools/eval-run.py`.
