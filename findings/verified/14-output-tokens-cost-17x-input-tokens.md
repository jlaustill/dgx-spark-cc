---
id: "14"
status: verified
title: Output tokens cost about 17x more than input tokens
measured: 2026-08-15
supersedes: "The original figure of ~38x, which divided shallow prefill (473 t/s) by deep decode (12.45 t/s). Those are different depths and the ratio is not meaningful. The claim that improving prefill widens the gap rested on the 38x figure and is dropped."
see_also: ["00", "17"]
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

## Limits

**Keep the magnitude honest.** Decode was 11.1 minutes of the 84.5 minutes in the
case study. Halving the thinking output saves about 5 minutes. Redundant prefill
was 57.9 minutes. This is a real lever and a small one. See
[17](17-case-study-84-5-minutes-of-model-time.md).
