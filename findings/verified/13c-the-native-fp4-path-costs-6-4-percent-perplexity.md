---
id: "13c"
status: verified
title: The native FP4 path costs 6.4 percent perplexity
measured: 2026-08-12
supersedes: "The original treatment of the native FP4 path as a pure win. The accuracy side was never measured."
see_also: ["07a", "13a", "13b"]
---

# The native FP4 path costs 6.4 percent perplexity

**Claim.** The native FP4 path is a speed and accuracy trade, not a pure win.
Turning it off makes the model measurably **more** accurate.

## Evidence

| | PPL |
|---|---:|
| native FP4 path (default) | **8.0227** |
| dequant path (ablated) | **7.5423** |

That is a 6.4% cost in perplexity.

## The mechanism

`use_native_fp4` selects `block_fp4_mmq` for the **activations**, which is
4-bit. The dequant route uses `block_q8_1_mmq`, which is 8-bit.

## What this changes

Both the original #7 and the original #13 presented the native FP4 path as a pure
win. It is not.

Whether 1.16x to 1.34x of prefill is worth 6.4% of perplexity is a judgement. The
person making it should make it knowingly.

For the speed side, see
[13b](13b-the-native-path-is-worth-1-16x-to-1-34x.md).
