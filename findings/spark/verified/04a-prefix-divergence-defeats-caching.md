---
id: "04a"
status: verified
title: Prefix divergence is the real cost, and no cache design fixes it
measured: 2026-08-15
see_also: ["11a", "15a"]
---

# Prefix divergence is the real cost, and no cache design fixes it

**Claim.** Tokens after a divergence point have changed. Their K and V values
have never been computed in that context. No storage tier substitutes for
arithmetic that has not happened.

**Cache design is not the lever. Not diverging is the lever.**

## Evidence

Measured on llama.cpp, the divergence sits at **6.5% to 6.7% depth**. A system
message enters about 9,700 tokens into a prompt of about 150,000 tokens.

An idealised cache holding a snapshot at every token would still re-read 93% of
the prompt. It recovers almost nothing.

## Limits

The original `ds4-server` event described under this heading diverged at about
**29.7% depth**, at token 119,600 of 402,000. That is not the same phenomenon as
the 6.5% head insertion. See
[04b](../unverified/04b-the-29-7-percent-divergence-event.md).

The conclusion above rests on the llama.cpp measurement and holds independently
of that unexplained event.
