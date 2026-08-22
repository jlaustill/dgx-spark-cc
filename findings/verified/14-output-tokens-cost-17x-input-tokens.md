---
id: "14"
status: verified
title: Output tokens cost about 17x more than input tokens
measured: 2026-08-15
supersedes: "The original figure of ~38x, which divided shallow prefill (473 t/s) by deep decode (12.45 t/s). Those are different depths and the ratio is not meaningful. The claim that improving prefill widens the gap rested on the 38x figure and is dropped."
see_also: ["00", "15b", "17"]
---

# Output tokens cost about 17x more than input tokens

**Claim.** At matched depth of about 116k tokens, writing a token costs about 17
times what reading a token costs. This follows directly from the batching
asymmetry in [00](00-capacity-for-bandwidth.md).

## Evidence

| | Rate | Relative cost |
|---|---:|---:|
| Reading input (prefill) | 210.5 t/s | 1x |
| Writing output (decode) | 12.44 t/s | **~17x** |

## Why it matters

V4 Flash is a reasoning model, so a large fraction of every response is
deliberation that the user never sees.

This inverts a habit carried over from hosted models, where input is the thing
you economise:

- Terser system prompts help twice. There is less to read, and less to imitate.
- Lower the reasoning effort where a task does not need deliberation.
- Ask for code rather than for code plus explanation.

## How large this lever is depends on whether the template fix is applied

**Before the fix it was small.** Decode was 11.1 minutes of the 84.5 minutes in
the case study, which is 13.1%. Redundant prefill was 57.9 minutes. Halving the
thinking output would have saved about 5 minutes against that 57.9. See
[17](17-case-study-84-5-minutes-of-model-time.md).

**After the fix it is the largest remaining lever.** The first production session
with the patched template measured:

| | tokens | time | share |
|---|---:|---:|---:|
| prefill | 66,134 | 4.2 min | 36% |
| **decode** | 5,956 | **7.5 min** | **64%** |
| redundant prefill | **0** | 0.0 min | 0% |

Removing redundant prefill does not make decode faster. It makes decode the
majority of what is left. The three recommendations above move from marginal to
primary. Raw output is in `data/bench/V15-production-session-20260822.log`, and
the fix that caused the shift is
[15b](15b-inline-rendering-removes-96-percent-of-redundant-prefill.md).

⚠️ The two sessions ran different tasks at different depths, so the wall-clock
totals are not comparable. The comparable figures are the shares.
