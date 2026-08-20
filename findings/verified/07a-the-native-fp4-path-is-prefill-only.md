---
id: "07a"
status: verified
title: MXFP4 has hardware acceleration on GB10 for prefill only
measured: 2026-08-12
supersedes: "The original claim, which did not bound the acceleration to prefill and implied it applied to decode as well."
see_also: ["07b", "13a", "13b", "13c"]
---

# MXFP4 has hardware acceleration on GB10 for prefill only

**Claim.** GB10 has a native FP4 path. That path governs exactly one compute
route, which is the batched matmul used by prefill. Decode has no native FP4 path
at all.

## Evidence

In `ggml/src/ggml-cuda/mmq.cu:131`:

```c
const bool use_native_fp4 = blackwell_mma_available(cc) &&
    (src0->type == GGML_TYPE_MXFP4 || src0->type == GGML_TYPE_NVFP4);
```

`blackwell_mma_available()` gates on `cc >= BLACKWELL && cc < RUBIN`, at
`common.cuh:360`. GB10 reports **12.1**, so it qualifies.

`mmq.cu` handles the batched matmul, which is prefill.

Decode goes through `mmvq.cu`. That file handles MXFP4 with
`vec_dot_mxfp4_q8_1`, which is a **dequantising** vec-dot with **no Blackwell
gate at all**, at `mmvq.cu:19`.

## The bytes-per-parameter argument stands separately

| Format | Bytes/param |
|---|---:|
| fp16 | 2.00 |
| Q8_0 | ~1.06 |
| **MXFP4** | **~0.56** |

This is a **bandwidth** argument. It is not a hardware-acceleration argument, and
the two must not be merged.

## Limits

Fewer bytes help decode only if the box can read them at the same rate. On this
chip it cannot. See
[07b](../refuted/07b-mxfp4-outdecodes-q8-0.md).

The prefill acceleration is real and measured. See
[13b](13b-the-native-path-is-worth-1-16x-to-1-34x.md). It also costs accuracy.
See [13c](13c-the-native-fp4-path-costs-6-4-percent-perplexity.md).
