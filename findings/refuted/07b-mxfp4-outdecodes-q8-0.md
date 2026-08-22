---
id: "07b"
status: refuted
title: "REFUTED: gpt-oss MXFP4 out-decodes Qwen Q8_0 by 1.21x"
measured: 2026-08-12
replaced_by: ["07a", "07d"]
see_also: ["08a"]
---

# REFUTED: gpt-oss MXFP4 out-decodes Qwen Q8_0 by 1.21x

**The refuted claim.** Decode is bandwidth-bound, so the model that reads fewer
bytes per token decodes faster. gpt-oss-120b has 5.1B active parameters in MXFP4
at about 2.9 GB per token. Qwen3-Coder-30B has 3.3B active parameters in Q8_0 at
about 3.5 GB per token. The arithmetic predicts that gpt-oss decodes
**1.21x faster**.

**What the measurement shows.** gpt-oss decodes at **0.79x**. It is slower, not
faster.

| | decode (tg64) |
|---|---:|
| Qwen3-Coder-30B Q8_0 | **63.34 +/- 0.48 t/s** |
| gpt-oss-120b MXFP4 | **50.21 +/- 0.23 t/s** |

Measured at matched shallow depth. The prediction misses by a factor of about
1.5, which is far outside the ~4% noise floor established in
[08b](../verified/08b-the-bench-noise-floor-is-4-percent.md).

**A prediction was written down and reality contradicted it. That is what this
file records.**

## What this does NOT establish

This is a comparison between **two different models**, not between two formats.
gpt-oss and Qwen differ in architecture, layer count, total parameter count, MoE
expert-gather traffic and attention type. Format is one of many variables, and it
is not controlled.

[08a](../verified/08a-there-is-no-universal-prefill-ceiling.md) states the rule
that applies here: **cross-model rows are indicative and same-model rows are
evidence.** By that rule this measurement refutes the specific prediction above,
and it does not refute or establish anything about MXFP4 as a format.

The wider claim, that MXFP4 decodes slower as a **format**, has since been tested
on one model with format as the only variable. It is false. MXFP4 decodes
**1.36x faster** than Q8_0. See
[07d](../verified/07d-mxfp4-decodes-faster-than-q8-0.md).

So the gap measured here belongs to the two models and not to their formats,
exactly as the cross-model rule predicts.

## Why this is worth keeping

The bytes-per-parameter arithmetic is correct and the conclusion still does not
follow. Anyone sizing a model by active parameters times bytes per parameter will
make this same prediction, and on this box it was wrong by 1.5x in the wrong
direction.
