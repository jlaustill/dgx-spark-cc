# E5 — the rope-stretch tolerance threshold

**Date:** 2026-08-18 · **Verdict: there is no threshold in the stretch factor.
The predictor is the ratio between applied and trained scaling.**

## Method

Qwen3-Coder-30B-A3B-Instruct-Q8_0, one corpus, one variable per pass.
`--rope-scaling yarn --rope-scale N` against `-c DEPTH`, one chunk at full depth.
Scale 1.0 passes no rope flags at all, so the control is the untouched vendor
config rather than the same value re-asserted.

Perplexity on this harness is deterministic to four decimal places, so every
difference below is caused by the flag and nothing else.

## Result

Absolute perplexity, and the change against each depth's own control:

| depth | x1.0 | x1.25 | x1.5 | x2.0 | x4.0 |
|---|---:|---:|---:|---:|---:|
| **8,192** | 5.7875 | 5.7361 | 5.6992 | 5.6649 | **5.6040** |
| | — | −0.89% | −1.53% | −2.12% | **−3.17%** |
| **32,768** | 2.4338 | 2.4330 | 2.4340 | 2.4384 | **2.4541** |
| | — | −0.03% | +0.01% | +0.19% | **+0.83%** |
| **131,072** | 2.0498 | 2.0462 | 2.0480 | 2.0495 | **2.0988** |
| | — | −0.18% | −0.09% | −0.01% | **+2.39%** |

Controls differ by depth because more context makes prediction easier. Compare
down a column only against the control in that row.

## What it means

**Stretching Qwen is nearly free.** The worst point across 15 passes is +2.39%.
The same flag on gpt-oss-120b at its ceiling gave **+3,281%** (PPL 2.7940 to
94.4541, V9.2).

**A stretch factor alone is not the threshold.** x4.0 *improves* Qwen by 3.17% at
8,192 tokens and costs 2.39% at 131,072. Same model, same corpus, same flag,
opposite sign.

**The mechanism is mismatch, not extrapolation.** `--rope-scale N` divides
positions by N. It compresses the angular range and never pushes a position past
the trained limit. So the damage is not running off the end of the window. It is
the distance between the mapping applied at inference and the mapping the model
learned:

- Qwen ships **no** vendor YaRN. Applying x2 is a small perturbation of a mapping
  learned at x1.
- gpt-oss ships YaRN at **factor 32**. Applying x2 gives an effective x64. Every
  position lands at an angle the model never saw.

That is why the same flag is harmless on one model and catastrophic on the other.

**Depth still matters, but as a multiplier on the mismatch.** x4.0 costs 0.83% at
32,768 and 2.39% at 131,072 — roughly triple for a 4x depth increase.

## The document's #9 claim

#9 proposes comparing models by **base length and stretch factor** rather than by
the presence of scaling:

| Model | Base | Factor | Result |
|---|---:|---:|---|
| DeepSeek V4 Flash | 65,536 | x16 | 1M |
| gpt-oss-120b | 4,096 | x32 | 131k |

**That instinct is supported.** The vendor factor is what determines how much
headroom an added stretch has. A model already at x32 has almost none. A model at
x1 has a great deal.

**But the table does not answer E5 by itself.** It compares two models that also
differ in weights, architecture and training data. This test sweeps one model and
cannot make a cross-model claim.

## What this test did not measure

**262,144 tokens is not reachable on this machine.** `llama-perplexity` holds the
logits for the whole context, a buffer of `n_ctx x n_vocab x 4` bytes. Qwen's
vocabulary is 151,936 tokens:

| context | logits buffer | |
|---|---:|---|
| 131,072 | 74.2 GiB | fits, barely |
| 262,144 | **148.4 GiB** | exceeds the 121 GB box |

The run fails with `std::bad_alloc`. E5's original framing — "Qwen at 262k vs
524k" — was never runnable here, and the plan that proposed it did not do this
arithmetic first.

Qwen at 131,072 is therefore at **half** its native window. A stretch at its true
ceiling is untested. The trend across three depths is consistent and the gap to
gpt-oss is three orders of magnitude, so the conclusion is unlikely to reverse,
but it rests on three rows rather than four.

**Perplexity is not task success.** The eval harness (`tools/eval-run.py`) can
score stretch factors on 10 real tasks. That stage is not run.
