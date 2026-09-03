---
id: "02"
status: unverified
title: MoE expert offload is linear in the fraction offloaded, with no knee
measured: 2026-09-03
see_also: ["01", "04", "05"]
---

# MoE expert offload is linear in the fraction offloaded, with no knee

**Claim.** Sweeping `--n-cpu-moe` on Qwen3-Next-80B produces a straight line, not
a cliff. Moving 8 of 48 expert layers onto the GPU buys 16% decode — almost
exactly proportional. There is no threshold to find, and the knob's entire
authority is ~17%.

## Evidence

`llama-bench`, Qwen3-Next-80B-A3B-Thinking-UD-Q6_K_XL (63.81 GiB), `-ngl 99`,
`-p 2048 -n 128 -r 3`, one launch per point. VRAM is the peak sampled at 1 Hz
during the run.

| `-ncmoe` | expert layers on GPU | VRAM MiB | pp2048 t/s | tg128 t/s | vs 48 |
|---:|---:|---:|---:|---:|---:|
| 48 | 0 | 3,469 | 253.8 | 26.75 | 1.00x |
| 47 | 1 | — | 258.8 | 26.93 | 1.01x |
| 46 | 2 | 6,733 | 264.6 | 28.24 | 1.06x |
| 45 | 3 | — | 271.2 | 28.61 | 1.07x |
| 44 | 4 | 9,625 | 275.9 | 29.02 | 1.08x |
| 43 | 5 | — | 282.6 | 29.82 | 1.11x |
| 42 | 6 | 12,517 | 287.6 | 31.12 | 1.16x |
| 41 | 7 | — | 292.0 | **31.20** | 1.17x |
| 40 | 8 | 15,037 | 295.6 | 31.09 | 1.16x |
| 38 | 10 | **OOM** | — | — | — |

**A 63.81 GiB model runs on a 16 GB card**, at 26.75 t/s with every expert on
the CPU.

## VRAM is linear at 1,446 MiB per expert layer

(15,037 - 3,469) / 8 = 1,446 MiB. That linearity is what makes the ceiling
predictable: usable `-ncmoe` is set by whatever VRAM the KV cache leaves behind.

## The knob trades decode against context, gently

At `-ncmoe 40` only ~800 MiB of VRAM remains. 128k of context costs ~4,250 MiB
at the 33.2 KiB/token measured in
[spark/20](../../spark/verified/20-context-costs-more-than-the-kv-formula-says.md),
which forces about 3 expert layers back to the CPU — roughly `-ncmoe 43`, or
~29.8 t/s. So the **full 128k of context costs about 4% of decode.** At 262144
the ceiling is `-ncmoe 46`; 45 aborts with `CUDA error: out of memory`.

## Why this is unverified

**One launch per point.** The floor in
[05](../verified/05-back-to-back-launch-variance.md) was measured on a different
model, fully resident in VRAM. An offloaded configuration touches PCIe and DDR5
every token and may be noisier, so these points have no applicable error bar.

That matters most for the apparent peak at `-ncmoe 41` (31.20) and dip at 40
(31.09). The difference is 0.35%. It is plausibly real — at 40 the card is at
95% occupancy and allocator pressure could cost something — but it is **not
claimed**.

Prefill here is also not comparable to
[04](../verified/04-the-spark-wins-both-halves-on-qwen3-next.md): this sweep ran
at llama-bench's default `-ub 512`, while the server arm used `-ub 2048` per
[spark/12a](../../spark/verified/12a-ubatch-2048-buys-19-to-31-percent-of-prefill.md).

**Completing test.** Four independent launches at `-ncmoe` 48, 44 and 40, giving
each point an error bar, plus a repeat at `-ub 2048` so the sweep and the
cross-box arm share a configuration.
