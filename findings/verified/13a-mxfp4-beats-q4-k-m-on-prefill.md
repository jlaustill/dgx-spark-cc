---
id: "13a"
status: verified
title: MXFP4 beats Q4_K_M on prefill by 1.19x to 1.47x
measured: 2026-08-12
see_also: ["07a", "07d", "13b", "13c", "08a"]
---

# MXFP4 beats Q4_K_M on prefill by 1.19x to 1.47x

**Claim.** With format as the only variable, MXFP4 prefills 1.19x to 1.47x faster
than Q4_K_M.

## The controlled experiment

One model (gpt-oss-120b), one harness, one architecture, 5.1B active parameters
either way. The MXFP4 file was requantised in place to Q4_K_M, so **format is the
only variable**.

| Test | ub | MXFP4 | Q4_K_M | Ratio |
|---|---:|---:|---:|---:|
| pp4096 | 2048 | 2332 t/s | 1786 t/s | **1.31x** |
| pp16384 | 2048 | 2187 t/s | 1704 t/s | 1.28x |
| pp65536 | 2048 | 1555 t/s | 1307 t/s | 1.19x |
| pp4096 | 512 | 1801 t/s | 1265 t/s | **1.43x** |
| pp16384 | 512 | 1732 t/s | 1211 t/s | 1.43x |
| pp65536 | 512 | 1310 t/s | 985 t/s | 1.33x |

Re-measured on the same commit, the ratios hold:

| Test | ub | ratio (published) | ratio (re-measured) |
|---|---:|---:|---:|
| pp4096 | 2048 | 1.31x | **1.30x** |
| pp16384 | 2048 | 1.28x | **1.29x** |
| pp65536 | 2048 | 1.19x | **1.20x** |
| pp4096 | 512 | 1.43x | **1.47x** |
| pp16384 | 512 | 1.43x | **1.42x** |
| pp65536 | 512 | 1.33x | **1.36x** |

## The levers stack

MXFP4 at `ub 2048` is **1.847x** faster than Q4_K_M at `ub 512`, at 2355.89
against 1275.60 t/s. This matches the originally reported 1.84x.

The ubatch lever is **larger** for the dequant format. Q4_K_M gains +41.7%,
+42.3% and +34.2% from `ub 2048`, against MXFP4's +25.8%, +30.0% and +18.7%.
An arithmetic-intensity explanation predicts exactly this. The format that pays
more per weight-read benefits more from amortising that read.

The advantage is largest at small ubatch and shallow depth, where matrix-multiply
dominates and attention does not. A dequantisation-avoidance explanation predicts
this too.

## Limits

This ratio is the **combined** effect of two differences. MXFP4 takes the native
path, and MXFP4 is also smaller. See
[13b](13b-the-native-path-is-worth-1-16x-to-1-34x.md) for the decomposition.

The speed is not free. See
[13c](13c-the-native-fp4-path-costs-6-4-percent-perplexity.md).

**This experiment covers prefill only.** The equivalent same-model comparison for
decode was run separately, on Qwen rather than gpt-oss, and it also favours
MXFP4. See [07d](07d-mxfp4-decodes-faster-than-q8-0.md).
