---
id: "07b"
status: refuted
title: "REFUTED: MXFP4's fewer bytes make it decode faster than Q8_0"
measured: 2026-08-12
replaced_by: ["07a"]
---

# REFUTED: MXFP4's fewer bytes make it decode faster than Q8_0

**The refuted claim.** Decode is bandwidth-bound, so the format that reads fewer
bytes per parameter decodes faster. gpt-oss-120b has 5.1B active parameters in
MXFP4 at about 2.9 GB per token. Qwen3-Coder-30B has 3.3B active parameters in
Q8_0 at about 3.5 GB per token. The arithmetic predicts gpt-oss decodes
**1.21x faster**.

**What the measurement shows.** gpt-oss decodes at **0.79x**. It is slower, not
faster.

| | decode | effective bandwidth |
|---|---:|---:|
| Qwen3-Coder-30B Q8_0 | **63.34 t/s** | 221 GB/s |
| gpt-oss-120b MXFP4 | **50.21 t/s** | 143 GB/s |

Measured at matched shallow depth.

## Why the arithmetic misleads

The arithmetic is correct. The conclusion does not follow from it.

MXFP4 achieves only 143 GB/s of effective bandwidth against Q8_0's 221 GB/s.
Decode has no native FP4 path, so it pays `vec_dot_mxfp4_q8_1` dequantisation for
every byte. Q8_0 unpacks almost for free. See
[07a](../verified/07a-the-native-fp4-path-is-prefill-only.md).

**"Format beats parameter count here" is false on decode.** Fewer bytes help only
if you can read them at the same rate.

## Why this is worth keeping

This box has no single effective bandwidth figure, and this refutation is the
reason. Qwen reaches 221 GB/s and gpt-oss reaches 143 GB/s on the same hardware.
Anyone who quotes one number for the machine will mispredict the other model.
