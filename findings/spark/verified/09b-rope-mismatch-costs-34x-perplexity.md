---
id: "09b"
status: verified
title: A stacked rope flag degrades perplexity by 34x, and only at full context
measured: 2026-08-17
see_also: ["09a", "09c"]
---

# A stacked rope flag degrades perplexity by 34x, and only at full context

**Claim.** Passing rope flags on top of a config that already carries YaRN does
not merely make output worse. It destroys the model's output, silently, while the
server reports that it is healthy.

## Evidence

gpt-oss-120b MXFP4, one chunk at the model's full **131,072** context, with the
rope flag as the only variable:

| arm | PPL |
|---|---:|
| vendor config, no rope flags | **2.7940 +/- 0.02197** |
| `--rope-scaling yarn --rope-scale 2` | **94.4541 +/- 1.17464** |

That is a **34x degradation**. A perplexity of 94 is a model emitting near-noise.

## The corruption is invisible at short context

The same comparison at 2,048 tokens:

| context | no flags | `--rope-scale 2` | effect |
|---:|---:|---:|---|
| 2,048 | 4.7195 | 4.5520 | 3.5% *better* |
| 131,072 | 2.7940 | **94.4541** | **34x worse** |

At 2,048 the flag maps positions 0 to 2,047 onto 0 to 1,023. That range sits deep
inside the trained range, so the flag is harmless and even marginally helpful.

At 131,072 the flag maps positions onto 0 to 65,535. This halves the angular
spacing across the whole operating range, and the encoding collapses.

Perplexity here is bit-exact deterministic, so both numbers are the flag's doing
and nothing else.

## Why this matters for testing

**Anyone who tests this at a convenient short context will conclude that the
flags are harmless.** They are not. The test has to run at the ceiling.
