---
id: "09c"
status: verified
title: Rope damage tracks mismatch with the trained mapping, not the stretch factor
measured: 2026-08-18
see_also: ["09a", "09b"]
---

# Rope damage tracks mismatch with the trained mapping, not the stretch factor

**Claim.** There is no tolerance threshold in the stretch factor. The damage is
the distance between the mapping applied at inference and the mapping the model
learned. This answers experiment E5.

## Evidence

Qwen3-Coder-30B, one variable per pass, each depth against its own control:

| depth | x1.25 | x1.5 | x2.0 | x4.0 |
|---|---:|---:|---:|---:|
| 8,192 | -0.89% | -1.53% | -2.12% | **-3.17%** |
| 32,768 | -0.03% | +0.01% | +0.19% | +0.83% |
| 131,072 | -0.18% | -0.09% | -0.01% | **+2.39%** |

The worst point across 15 passes is **+2.39%**. The same flag on gpt-oss at its
ceiling gave **+3,281%**. See
[09b](09b-rope-mismatch-costs-34x-perplexity.md).

Note also that x4.0 **improves** Qwen by 3.17% at 8,192 while costing 2.39% at
131,072. That is the same model on the same corpus, with the sign reversed.

## The mechanism

`--rope-scale N` divides positions by N. It compresses the angular range and
never pushes past the trained limit. So extrapolation is not the mechanism.

Qwen ships no vendor YaRN, so x2 is a small perturbation of a mapping learned at
x1. gpt-oss ships factor 32, so x2 gives an effective x64, and every position
lands at an angle the model never saw.

## What this means for model selection

The comparable numbers are **base length** and **stretch factor**, not the
presence or absence of scaling:

| Model | Base | Factor | Result |
|---|---:|---:|---|
| DeepSeek V4 Flash | 65,536 | x16 | 1M |
| gpt-oss-120b | 4,096 | x32 | 131k |

The vendor factor determines how much headroom an added stretch has. A model
already at x32 has almost none. That is why x2 costs gpt-oss +3,281% while Qwen
at x1 barely moves.

## Limits

**This supports the table above. It does not prove it.** These two models differ
in weights, architecture and training data, so base-length-and-factor remains a
heuristic for model selection and not a measured law.

**262,144 is unreachable on this box.** `llama-perplexity` holds
`n_ctx x n_vocab x 4` bytes of logits. At Qwen's 151,936 vocab that is 148.4 GiB,
against 74.2 GiB at 131,072. Qwen was therefore tested at **half** its native
window, and a stretch at its true ceiling remains untested.

gpt-oss was rejected on this box for its **context ceiling**, not for its
quality. Its output was never evaluated.

## Background

RoPE has a fixed angular budget, and YaRN packs more positions into a budget
sized for fewer. Training on the stretched ruler teaches the model to read it.
Where two positions land on nearly identical angles, no amount of training
separates them, because the information is not in the encoding. YaRN is
deliberate about where it spends that loss. Its `beta_fast` and `beta_slow` ramp
between leaving high-frequency dimensions nearly untouched and compressing the
low-frequency, long-range ones.

Native training at 1M does not exist, and not by oversight. Attention is O(n^2),
and there are not enough genuine million-token documents to train on. Every
long-context model is extended in stages. "Native" is a spectrum and not a
binary.
