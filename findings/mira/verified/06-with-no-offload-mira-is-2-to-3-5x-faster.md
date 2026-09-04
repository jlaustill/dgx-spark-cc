---
id: "06"
status: verified
title: With nothing offloaded, mira is 2.1-2.4x on prefill and 3.1-3.5x on decode
measured: 2026-09-04
see_also: ["01", "03", "04"]
---

# With nothing offloaded, mira is 2.1-2.4x on prefill and 3.1-3.5x on decode

**Claim.** Given a model both machines hold entirely in fast memory, mira beats
spark on **every** measurement at **every** depth. The decode advantage **grows**
with context depth rather than shrinking.

This reverses the reading of
[04](04-the-spark-wins-both-halves-on-qwen3-next.md), which measured the two
boxes on a model mira cannot hold. **That result was the offload penalty, not
the hardware.**

## Method

Experiment [X1](../../../experiments/X1-resident-model-ratio/). gpt-oss-20b
MXFP4, 11.27 GiB, sha256-verified byte-identical on both boxes. llama.cpp
`687e778` both sides. `-p 4096 -n 128 -d 0,16384,65536 -ngl 99 -fa on -r 3`, two
independent launches per box, every llama-server stopped for the duration.

The model is chosen for one property only: it is the largest interesting model
that fits mira's ~15.8 GiB with room for KV at depth, so **neither box offloads
anything**. Its unfitness for agentic work
([spark/15e](../../spark/verified/15e-gpt-oss-drops-mid-conversation-system-messages.md))
does not touch throughput.

## Result

| test | mira t/s | spark t/s | ratio |
|---|---:|---:|---:|
| pp4096 | 10,694.83 | 4,404.89 | **2.43x** |
| tg128 | 241.78 | 79.05 | **3.06x** |
| pp4096 @ d16384 | 7,977.98 | 3,287.25 | **2.43x** |
| tg128 @ d16384 | 213.68 | 66.60 | **3.21x** |
| pp4096 @ d65536 | 4,051.48 | 1,889.29 | **2.14x** |
| tg128 @ d65536 | 162.25 | 46.91 | **3.46x** |

## The decode gap widens with depth

3.06x -> 3.21x -> 3.46x from d0 to d65536. This is the direction that matters:
agentic coding runs deep, and the advantage is largest exactly there. Prefill
moves the other way, 2.43x -> 2.14x, but never below 2x.

## The bandwidth model predicted this to 0.3%

Applying [spark/06a](../../spark/verified/06a-shallow-decode-is-bandwidth-bound.md)'s
formula, `active_params x bytes_per_param x t/s`, to the same model on both
boxes:

| | achieved |
|---|---:|
| mira | **504 GB/s** |
| spark | **165 GB/s** |

504 / 165 = **3.07x** against **3.06x** measured directly at tg128. Two
independent routes to the same number, one of them computed before the
measurement existed. The gap is GDDR7 against LPDDR5X and nothing else.

## What this says about upgrading

mira's VRAM is a purchase; spark's 121 GB is welded on. Everything mira lost in
[04](04-the-spark-wins-both-halves-on-qwen3-next.md) it lost to having nowhere
to put the weights, at ~58 GB/s across DDR5-3600.

If the 3.07x bandwidth ratio carries to a resident Qwen3-Next-80B, spark's
measured 41.47 t/s implies roughly **127 t/s** on mira. That requires ~72 GiB
for Q6_K_XL at 256k, or ~51 GiB at Q4_K_XL. **That last figure is a projection,
not a measurement** — it assumes the ratio is a property of the memory systems
and not of gpt-oss.

## Limits

**One model.** The ratio is measured on gpt-oss-20b MXFP4 only. It should hold
wherever both boxes are bandwidth-bound and fully resident, which is the regime
decode lives in, but that is an argument rather than a second data point.

**One soft number.** spark's `pp4096 @ d65536` spread 3.65% between launches
against under 1.1% everywhere else. Nothing here leans on that row, and it wants
a third launch before anything does.

**Throughput, not quality.** This says nothing about which box solves more
tasks. gpt-oss-20b in particular is unfit for the agentic workload.

**Multi-GPU is untested.** Reaching 51 GiB means two cards, and llama.cpp then
splits by layer with activations crossing PCIe. Decode should tolerate that;
"should" is doing real work in that sentence.
