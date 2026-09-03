---
id: "22"
status: verified
title: Qwen3-Coder-Next's context ceiling was the server, not the model
measured: 2026-08-26
see_also: ["09a", "09b", "09c", "19", "21"]
---

# Qwen3-Coder-Next's context ceiling was the server, not the model

**Claim.** Qwen3-Coder-Next retrieves correctly at **516,180 tokens**, nearly
twice its documented 262,144 context, **without rope scaling of any kind**. The
HTTP 400 that looked like a model limit came from an unconditional clamp in
`llama-server`. Lifting the clamp is sufficient. No rope flag is needed, and
passing one is mildly harmful.

## Evidence

Three needles per haystack at 20%, 50% and 80% depth, each a code that cannot be
guessed, asked as separate turns sharing one prefill. Scoring is exact substring
match.

| arm | rope | cap | 131k | 254k | 393k | 516k |
|---|---|---|---:|---:|---:|---:|
| native | none | on | 3/3 | 3/3 | *HTTP 400* | *HTTP 400* |
| yarn x2 | x2 | on | 3/3 | 3/3 | *HTTP 400* | *HTTP 400* |
| yarn x2 | x2 | **off** | — | 3/3 | **3/3** | **3/3** |
| **naive** | **none** | **off** | — | — | **3/3** | **3/3** |

At 516,180 tokens the 20% needle sits about **413,000 tokens before the
question**. Cold prefill was 460 s at 393k and 703 s at 516k; follow-up turns on
the same prefix were 5–6 s.

## The clamp

`tools/server/server-context.cpp:1310`, unconditional, no flag:

```c
int n_ctx_slot = llama_n_ctx_seq(ctx_tgt);
if (n_ctx_slot > n_ctx_train) {
    SRV_WRN("the slot context (%d) exceeds the training context ... - capping\n", ...);
    n_ctx_slot = n_ctx_train;
}
```

Note what it does: it caps the context **and applies the rope flags anyway**.
That is [09a](09a-rope-flags-are-silently-applied.md) reproducing on a second
model. Both "capped" rows above are therefore rope-flagged, context-capped
servers — valid as an A/B on the mapping, and silent about depth.

`tools/patches/e8-allow-ctx-overflow.patch` gates the clamp on
`LLAMA_ALLOW_CTX_OVERFLOW`. It is inert unless the variable is set.

## The rope flag is unnecessary, and it is not free

The `naive` arm is the control. It passes 3/3 at both depths beyond the trained
ceiling with **no rope flags at all**, matching the scaled arm exactly. So the
flag is not what makes deep context work.

The flag was not a no-op being mistaken for a null result. Perplexity is
bit-exact deterministic, and at 8,192 tokens the same flag moved it
**1.5888 → 1.6088**, a 1.26% cost. It is applied, it does change the model, and
at depth it changes nothing that this probe can see.

**So: raise `--ctx-size`, pass no rope flags.**

## Why the model tolerates it — untested

`rope_theta` is 5,000,000 with `partial_rotary_factor` 0.25, and only 12 of 48
layers use rope at all; the other 36 are DeltaNet with no positional encoding to
get wrong. That is a plausible mechanism and nothing here measures it. It is
recorded so nobody mistakes it for a result.

## Limits

**Retrieval is a weak probe.** It shows the model can locate and copy a
distinctive string across 400k+ tokens. It does **not** show that reasoning
quality holds there. A model can be perfect at needle recall and degraded at
everything else.

**Perplexity, the stronger probe, cannot run at these depths on this box.**
`llama-perplexity` reserves `n_ctx * n_vocab * 4` bytes of logits: 148 GiB at
262,144 with a 151,936 vocab. It dies in `std::bad_alloc` above roughly 98,304.
This also explains a gap in [09c](09c-damage-tracks-mismatch-not-stretch-factor.md),
whose table stops at 131,072 — its `d262144-*.log` files are this same crash, and
the finding does not say so.

**The vendor documents 262,144 and no YaRN config.** This is past what Qwen
supports. The measurement says retrieval survives; the vendor says nothing about
it either way.

**One corpus, one needle format, one quant.**

## Completing test

Run `tools/eval-run.py` with the context filled past 262,144 and compare task
success against the same eval at 100k. That measures reasoning at depth rather
than recall, which is the claim this finding deliberately does not make.

## Applied

`qwen3next-server.sh` now defaults to `--ctx-size 524288` and exports
`LLAMA_ALLOW_CTX_OVERFLOW=1`. On an unpatched binary the variable is ignored and
the server caps silently — check the startup log for "NOT capping".

Deeper contexts also make prompt-cache entries larger: a 516k conversation is
~16.6 GiB of saved state against the 24 GiB `--cache-ram` set in
[21](../unverified/21-the-default-prompt-cache-is-too-small.md). That threshold
was chosen for 262,144 and will need revisiting; 21's completing test now needs
re-baselining against this configuration rather than the one it was written for.
