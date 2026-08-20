---
id: "07c"
status: refuted
title: "REFUTED: MXFP4 decodes slower because decode pays dequantisation"
measured: 2026-08-20
replaced_by: ["07d"]
see_also: ["07a", "07b", "08a"]
---

# REFUTED: MXFP4 decodes slower because decode pays dequantisation

**The refuted claim.** Decode does not enter the native FP4 path, so an MXFP4
model pays `vec_dot_mxfp4_q8_1` dequantisation for every byte it reads. Q8_0
unpacks more cheaply. MXFP4 therefore decodes slower than its byte count
predicts.

**What the measurement shows.** MXFP4 decodes **1.36x faster** than Q8_0 on the
same model. Fewer bytes win on decode, and they win by a wide margin.

| test | Q8_0 (30.25 GiB) | MXFP4 (15.90 GiB) | ratio |
|---|---:|---:|---:|
| tg64, launch 1 | 64.49 +/- 0.42 | **87.72 +/- 0.51** | **1.360x** |
| tg64, launch 2 | 64.45 +/- 0.28 | **87.38 +/- 0.89** | **1.356x** |
| tg64 @ d16384, launch 1 | 41.94 +/- 1.88 | 52.54 +/- 0.13 | 1.253x |
| tg64 @ d16384, launch 2 | 42.98 +/- 0.10 | 52.54 +/- 0.37 | 1.222x |

Qwen3-Coder-30B-A3B, one model, two quantisations, three repetitions each. The
model order was reversed between launches. The between-launch spread is 0.4% for
MXFP4 and 0.06% for Q8_0, well inside the ~4% noise floor from
[08b](../verified/08b-the-bench-noise-floor-is-4-percent.md). Raw output is in
`data/bench/V7.4-decode-qwen-mxfp4-vs-q8_0.log`.

## Why the original reasoning failed

The claim rested on a comparison between **two different models**, gpt-oss MXFP4
against Qwen Q8_0, at
[07b](07b-mxfp4-outdecodes-q8-0.md). That comparison did not control format.

Now that format **is** the only variable, the sign reverses. The 0.79% gap
between gpt-oss and Qwen was a property of the two models, not of their weight
formats.

This is the second time in this document that a cross-model comparison produced a
confident and wrong conclusion.
[08a](../verified/08a-there-is-no-universal-prefill-ceiling.md) already stated
the rule: cross-model rows are indicative and same-model rows are evidence.

## What survives

Dequantisation on decode is not free, and this measurement bounds it rather than
eliminating it. The MXFP4 file is **1.90x** smaller and decode is only **1.36x**
faster. Something absorbs the rest of the byte saving.

Two candidates, and this experiment does not separate them:

1. `MXFP4_MOE` converts only the expert tensors. Attention, norms and embeddings
   stay Q8_0 in both arms, so the bytes a token reads did not fall by the full
   file ratio.
2. `vec_dot_mxfp4_q8_1` costs more per byte than the Q8_0 unpack.

**The claim that dequantisation cost dominates is dead.** The claim that it
exists is untouched and unmeasured. See
[07d](../verified/07d-mxfp4-decodes-faster-than-q8-0.md).

## Why this is worth keeping

The reasoning was mechanically sound and reached the wrong answer. It read the
correct fact from source, that decode never enters the native FP4 path, and then
assumed that the missing hardware path must cost speed. On a memory-bound
workload it does not, because the multiply was never the bottleneck.
