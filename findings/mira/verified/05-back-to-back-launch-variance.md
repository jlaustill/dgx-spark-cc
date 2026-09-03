---
id: "05"
status: verified
title: Back-to-back launch variance here is 0.45 percent, and is not spark's 4.3
measured: 2026-09-03
see_also: ["02"]
---

# Back-to-back launch variance here is 0.45 percent, and is not spark's 4.3

**Claim.** Four independent launches of one binary, back to back, spread 0.45%
on prefill and 0.13% on decode. Differences above ~1% measured in a single
sitting on this box are resolvable.

## Evidence

`llama-bench -m gpt-oss-20b-MXFP4.gguf -p 4096 -n 128 -ub 512 -ngl 99 -r 3`,
four separate process launches, quiet disk, GPU idle at 36 C beforehand:

| launch | pp4096 t/s | within-run sigma | tg128 t/s | within-run sigma |
|---|---:|---:|---:|---:|
| 1 | 10,700.27 | 0.20% | 241.96 | 0.35% |
| 2 | 10,666.10 | 0.19% | 242.10 | 0.28% |
| 3 | 10,671.42 | 0.26% | 241.98 | 0.29% |
| 4 | 10,652.09 | 0.25% | 241.78 | 0.28% |
| **mean** | **10,672.47** | | **241.95** | |
| **spread** | **0.45%** | | **0.13%** | |

## This is not comparable to spark/08b, and must not be quoted as if it were

[spark/08b](../../spark/verified/08b-the-bench-noise-floor-is-4-percent.md)
reports a 4.3% floor. Its four rows are **the original published session, a
rebuilt baseline, a patched build and a reverted build** — three different
binaries across at least two sessions. This measures four launches of one binary
inside 20 seconds.

The two numbers describe different quantities. 08b's bundles build-to-build and
session-to-session drift; this one excludes both by construction. **Nothing here
says this box is quieter than the Spark.** Concluding that from these two
figures would be reading a protocol difference as a hardware difference.

What it does license: within one sitting, on one binary, the reported `+/-`
understates true spread by about 2x here, against the 10-40x seen in 08b's data.

## Limits

**One model, one row.** gpt-oss-20b MXFP4 fully resident in VRAM. An offloaded
configuration crosses PCIe and DDR5 every token and may well be noisier; the
sweep in [02](../unverified/02-moe-offload-is-linear-with-no-knee.md) is not
covered by this floor.

**The completing test** for a figure comparable to 08b is four launches
separated by rebuilds and by hours, on the same row.
