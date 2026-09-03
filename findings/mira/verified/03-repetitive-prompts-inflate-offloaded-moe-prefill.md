---
id: "03"
status: verified
title: A repetitive prompt inflates offloaded-MoE prefill by 69 percent
measured: 2026-09-03
see_also: ["01", "02", "04"]
---

# A repetitive prompt inflates offloaded-MoE prefill by 69 percent

**Claim.** Benchmarking an offloaded MoE with synthetic repetitive text measures
the repetitiveness, not the machine. The same prompt length of real source code
costs this box **41% of its apparent prefill throughput**, while costing the
Spark only 12%.

**A synthetic prompt produced a cross-box conclusion that was entirely an
artifact.** See Consequence.

## Evidence

Both prompts are exactly **29,701 tokens**, trimmed to that count through the
server's own `/tokenize`. Same model, same commit, same server flags, same
request. Only the character of the text differs.

- **synthetic**: one 171-character paragraph about KV caches, repeated 900 times
- **natural**: concatenated TypeScript from `jlaustill/c-next` `src/`

| | synthetic | natural | change |
|---|---:|---:|---:|
| **mira** prefill (`-ncmoe 46`) | 2,076.4 t/s | **1,225.6 t/s** | **-41.0%** |
| **spark** prefill | 1,501.4 t/s | **1,325.9 t/s** | -11.7% |

Natural-text figures are the mean of 3 reps. Spread was 0.45% on spark
(1329.2 / 1325.1 / 1323.3) and 1.5% on mira (1220.8 / 1218.8 / 1237.3), so the
gap is far outside run-to-run variation.

Stated the other way: the synthetic prompt inflates mira by **1.69x** and spark
by **1.13x**.

## Mechanism

A repeated paragraph routes to a narrow set of experts. The two machines pay
very differently for that:

- On **mira** the experts live in system RAM at ~58 GB/s. A narrow working set
  fits the 7950X3D's 128 MiB L3, so most expert reads stop reaching DRAM at all.
- On **spark** every expert sits in one uniform 121 GB pool at ~273 GB/s.
  Routing breadth changes little, because there is no slow tier to avoid.

So the sensitivity is not a property of MoE. It is a property of MoE **with a
memory hierarchy under it**, and it grows with the gap between the tiers.

## Consequence

The first cross-box comparison was run on the synthetic prompt and produced a
crossover rule: mira wins prefill 1.38x, spark wins decode 1.48x, so the better
box depends on a turn's prefill:decode ratio, break-even near 64:1.

**That crossover does not exist.** On natural text spark wins prefill *and*
decode, so no ratio makes mira the faster box for this model. See
[04](04-the-spark-wins-both-halves-on-qwen3-next.md).

## Limits

**One synthetic prompt and one natural prompt.** "Repetitive" and "natural" are
two points, not a scale. Nothing here says how prefill varies with a measured
diversity metric, only that the endpoints differ by 1.69x on this box.

The natural prompt is TypeScript from one repository. Prose, or a different
language, may route differently.

The synthetic figures are single runs; only the natural-text figures were
repeated. That biases nothing here — the effect is 41%, far beyond any plausible
single-run error — but the 2,076.4 and 1,501.4 values carry no error bar.

**The 128 MiB L3 is named as the mechanism, not measured as one.** No cache-miss
counters were read. The completing test is to re-run both prompts while
sampling LLC misses, or on a CPU with a small L3, and show the effect shrinks.
