---
id: "13b"
status: verified
title: The native FP4 path is worth 1.16x to 1.34x, and fewer bytes are worth 1.04x to 1.11x
measured: 2026-08-12
supersedes: "The original attribution of the full 1.19x-1.43x to the hardware path. That range is the combined effect of the path and the smaller file."
see_also: ["07a", "13a", "13c"]
---

# The native FP4 path is worth 1.16x to 1.34x, and fewer bytes are worth 1.04x to 1.11x

**Claim.** MXFP4 differs from Q4_K_M in two ways. It takes the native path, and
it is 59.0 GiB against 81.8 GiB. Separating the two shows that the hardware path
is the dominant term, but it is not the whole measured gain.

## Method

Separating the two effects needs a build with Blackwell MMA suppressed on
**both** host and device, using `-DGGML_NO_BLACKWELL_MMA` at `common.cuh:286` and
`common.cuh:360`. Suppressing it on one side only lets the two selectors
desynchronise.

**Q4_K_M is the control.** It never enters the FP4 branch, so the flag must be a
no-op for it. The flag is a no-op for it: 1275.60 to 1296.95, 997.50 to 1007.23,
and 1807.27 to 1819.86 t/s. All three sit inside the 4% noise floor. MXFP4 mean-
while slows by 15% to 24%.

## Result

| test | MXFP4/Q4_K_M pristine | ablated | native path worth |
|---|---:|---:|---:|
| pp4096 ub512 | 1.468x | 1.096x | **1.34x** |
| pp65536 ub512 | 1.361x | 1.109x | **1.23x** |
| pp4096 ub2048 | 1.304x | 1.059x | **1.23x** |
| pp65536 ub2048 | 1.204x | 1.037x | **1.16x** |

The native FP4 path is worth **1.16x to 1.34x**. Fewer bytes and cheaper
unpacking are worth only **1.04x to 1.11x**.

The hardware attribution is right in direction. The tensor-core path is the
dominant term. The originally published 1.19x to 1.43x is the combined effect and
not the path's own contribution.

## Limits

The branch bundles Blackwell FP4 MMA **and** 4-bit activations together. This
experiment therefore cannot prove that the tensor cores specifically account for
the 1.16x to 1.34x.

Separating those two would need a build that keeps FP4 MMA with 8-bit
activations. The code does not support that build.
