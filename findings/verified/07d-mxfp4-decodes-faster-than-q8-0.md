---
id: "07d"
status: verified
title: MXFP4 decodes 1.36x faster than Q8_0 on the same model
measured: 2026-08-20
see_also: ["06a", "07a", "07b", "07c", "13a"]
---

# MXFP4 decodes 1.36x faster than Q8_0 on the same model

**Claim.** With format as the only variable, MXFP4 decodes about 1.36x faster
than Q8_0 at shallow depth and about 1.24x faster at 16k depth. Decode is
bandwidth-bound on weights, so halving the expert weights buys speed even though
decode never uses the native FP4 path.

## The controlled experiment

One model, Qwen3-Coder-30B-A3B. The Q8_0 file was requantised to `MXFP4_MOE`, so
format is the only variable:

```bash
llama-quantize --allow-requantize \
  Qwen3-Coder-30B-A3B-Instruct-Q8_0.gguf \
  Qwen3-Coder-30B-A3B-MXFP4.gguf MXFP4_MOE 20
```

`MXFP4_MOE` sends the 3D expert tensors to MXFP4 and every other tensor to Q8_0,
at `llama-quant.cpp:474-481`. Both arms therefore hold the same model with every
tensor at Q8_0 except the expert weights. Each expert tensor halved, from 204 MiB
to 102 MiB, and the file went from 30.25 GiB to 15.90 GiB.

## Result

| test | Q8_0 | MXFP4 | ratio |
|---|---:|---:|---:|
| tg64, launch 1 | 64.49 +/- 0.42 | **87.72 +/- 0.51** | **1.360x** |
| tg64, launch 2 | 64.45 +/- 0.28 | **87.38 +/- 0.89** | **1.356x** |
| tg64 @ d16384, launch 1 | 41.94 +/- 1.88 | 52.54 +/- 0.13 | 1.253x |
| tg64 @ d16384, launch 2 | 42.98 +/- 0.10 | 52.54 +/- 0.37 | 1.222x |

Three repetitions per row. The model order was reversed between the two launches,
per [08b](08b-the-bench-noise-floor-is-4-percent.md). The between-launch spread is
0.4% for MXFP4 and 0.06% for Q8_0. Raw output is in
`data/bench/V7.4-decode-qwen-mxfp4-vs-q8_0.log`.

## What this confirms and what it bounds

It confirms [06a](06a-shallow-decode-is-bandwidth-bound.md). Decode is bound by
reading weights, so fewer weight bytes means faster decode. The native FP4 path
is irrelevant here, because the multiply was never the bottleneck. See
[07a](07a-the-native-fp4-path-is-prefill-only.md).

It bounds the cost of dequantisation without measuring it. The file is **1.90x**
smaller and decode is only **1.36x** faster. Two things could absorb the
difference, and this experiment does not separate them:

1. `MXFP4_MOE` leaves attention, norms and embeddings at Q8_0, so the bytes a
   token reads did not fall by the full file ratio.
2. `vec_dot_mxfp4_q8_1` may cost more per byte than the Q8_0 unpack.

## Limits

**One model, one engine, one commit.** Qwen3-Coder-30B-A3B on llama.cpp CUDA at
`687e778`. A second MoE model would establish repeatability, and none was tested.

**MoE only.** `MXFP4_MOE` is the sole MXFP4 target in `llama-quantize`, so this
comparison cannot be run on a dense model at all.

**The MXFP4 arm was requantised from Q8_0**, not from the original weights, so it
carries compounded quantisation error. That does not affect a speed measurement,
because block layout and byte count are identical either way. It would matter for
any accuracy claim, and no accuracy claim is made here.

**This is decode only.** For prefill, format behaves differently and the native
path does matter. See [13a](13a-mxfp4-beats-q4-k-m-on-prefill.md) and
[13b](13b-the-native-path-is-worth-1-16x-to-1-34x.md).
