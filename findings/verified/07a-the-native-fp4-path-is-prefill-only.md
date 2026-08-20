---
id: "07a"
status: verified
title: In llama.cpp CUDA, MXFP4 has hardware acceleration on prefill only
measured: 2026-08-12
supersedes: "The original claim, which did not bound the acceleration to prefill and implied it applied to decode as well."
see_also: ["07b", "07c", "07d", "13a", "13b", "13c"]
---

# In llama.cpp CUDA, MXFP4 has hardware acceleration on prefill only

**Scope.** This finding is about **llama.cpp's CUDA backend at commit
`687e778`**. It is not a statement about the GB10 silicon, and it is not a
statement about other engines. See Limits.

**Claim.** GB10 exposes a native FP4 path, and llama.cpp's CUDA backend uses it
on exactly one compute route: the batched matmul that prefill runs. The decode
route in that same backend never enters it.

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

`use_native_fp4` appears only in `mmq.cu`. `blackwell_mma_available()` is read in
three other places, and none of them selects an FP4 activation path:
`mmq.cuh:244` picks a tile config, `ggml-cuda.cu:5405` reports a build feature
string, and `common.cuh` defines the gate itself.

Routing decides which file runs. `ggml_cuda_should_use_mmq()` keys on the batch
dimension, at `ggml-cuda.cu:1861`. Decode has `ne11 == 1` and therefore routes to
`mmvq`.

## The bytes-per-parameter argument stands separately

| Format | Bytes/param |
|---|---:|
| fp16 | 2.00 |
| Q8_0 | ~1.06 |
| **MXFP4** | **~0.56** |

This is a **bandwidth** argument. It is not a hardware-acceleration argument, and
the two must not be merged.

## Limits

**This is a claim about one backend at one commit, not about the hardware.**
What is established is that llama.cpp's CUDA backend does not route decode
through the native FP4 path at `687e778`. Nothing here shows that the GB10
cannot do FP4 decode, only that this code does not ask it to. Upstream can add
an FP4 path to `mmvq` at any time and invalidate this finding without any
hardware changing.

**Within that backend the claim is model-independent.** The gate keys on the
tensor type, `GGML_TYPE_MXFP4` or `GGML_TYPE_NVFP4`, and not on the
architecture. Any model in either format decodes through the dequantising
vec-dot.

**Other engines are untested and this finding does not cover them.**

- **Ollama** vendors ggml, so models it runs through the llama.cpp engine
  probably inherit this behaviour. It was never run on this box, and it also has
  its own engine path for some models. Treat it as untested.
- **ds4-server** never ran an MXFP4 model here. It ran q2. Its only FP4 code is
  `dsv4_e2m1fn_dequant_dev()` in `ds4_cuda.cu:4198`, a software E2M1 helper
  inside V4's indexer Hadamard transform. That is not a weight matmul path and
  has no bearing on this claim.
- **vLLM and TensorRT-LLM** were not tested. NVIDIA's own stack ships FP4 kernels
  for Blackwell, so the claim may well be false there.

**Whether skipping the native path actually costs decode speed is a separate
question, and it is not answered here.** This finding establishes which code path
runs. It does not establish what that path costs. It has since been measured, and skipping
the native path costs decode nothing: MXFP4 decodes 1.36x **faster** than Q8_0 on
the same model, because decode is bound by reading weights and not by the
multiply. See [07d](07d-mxfp4-decodes-faster-than-q8-0.md). The two claims built
on the opposite assumption are refuted at
[07b](../refuted/07b-mxfp4-outdecodes-q8-0.md) and
[07c](../refuted/07c-mxfp4-decodes-slower-than-a-dequant-format.md).

The prefill acceleration is real and measured. See
[13b](13b-the-native-path-is-worth-1-16x-to-1-34x.md). It also costs accuracy.
See [13c](13c-the-native-fp4-path-costs-6-4-percent-perplexity.md).
