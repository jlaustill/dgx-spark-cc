---
id: "13d"
status: verified
title: A custom hybrid MXFP4 quant for V4 is not worth building
measured: 2026-08-12
see_also: ["12a", "13a", "13b"]
---

# A custom hybrid MXFP4 quant for V4 is not worth building

**Claim.** Promoting part of V4 to MXFP4 would gain 7% to 14% of prefill. One
free flag already gains more than that.

## Evidence

Read from V4's actual tensor list: V4 Flash UD-IQ3_XXS holds 284.3B parameters in
94.6 GiB. It is 63.4% IQ2_S, 31.0% IQ3_XXS, and already 1.5% MXFP4.

A pure MXFP4 build would be **140.7 GiB** and does not fit in 121 GB.

Inside a realistic 106 GiB weight budget, with the remainder pinned at the IQ2_S
floor, **only 40.1% of parameters can move to MXFP4**:

| native-path speedup on the promoted portion | overall gain |
|---|---:|
| 1.19x | **+6.8%** |
| 1.31x | **+10.5%** |
| 1.43x | **+13.7%** |

## The comparison that decides it

| Lever | Prefill gain | Cost |
|---|---:|---|
| `-ub 2048` | **+31%** | **one flag, already applied** |
| Custom hybrid MXFP4 | **+7 to +14%** | 144 GiB download, imatrix (days), requantise, eval |

The free flag delivers more than weeks of work would. See
[12a](12a-ubatch-2048-buys-19-to-31-percent-of-prefill.md).

## Limits

**This conclusion inverts if the tensor-core attribution is refuted.** If MXFP4
is fast because it is *smaller*, then promoting IQ2_S tensors at 2.5 bpw to MXFP4
at 4.25 bpw makes them larger, and therefore slower rather than faster. The
project would not be marginal. It would be backwards.

The attribution currently holds. See
[13b](13b-the-native-path-is-worth-1-16x-to-1-34x.md).
