---
id: "17"
status: verified
title: One real agentic session spent 68.6 percent of model time re-reading context
measured: 2026-08-10
see_also: ["04a", "11a", "12a", "14", "15a"]
---

# One real agentic session spent 68.6 percent of model time re-reading context

**Claim.** A single real agentic task used 84.5 minutes of model time. Redundant
prefill accounted for 57.9 of those minutes, which is 68.6%.

## Setup

A `/pr-check` skill run against a real open PR on a TypeScript compiler project,
at `jlaustill/c-next` #1140. DeepSeek-V4-Flash UD-IQ3_XXS, 1M ctx, q8_0 KV,
driven by Claude Code over `/v1/messages`.

## Result

```
DECODE   (writing output)     11.1 min      8,280 tok   12.45 t/s   13.1 %
PREFILL  (reading input)      73.4 min    858,025 tok   194.9 t/s
  necessary                   15.5 min    180,812 tok               18.3 %
  REDUNDANT                   57.9 min    677,213 tok               68.6 %
TOTAL model time              84.5 min
```

| Prefill events | Count |
|---|---:|
| Full re-reads (>20k tokens) | **6** |
| Incremental (<20k tokens) | 21 |
| Largest single prefill | 154,431 tok |

**68.6% of this machine's working life went to re-reading context it had already
read.** Decode accounted for 13%.

## Method note

These figures come from summing real per-task millisecond timings. They do not
come from dividing tokens by an average rate. Prefill rate varies from 190 to
210 t/s with depth, so the two methods are not interchangeable.

Every figure reproduces from the raw log.

## Limits

`necessary` is a **lower bound**. It is defined as the largest single prefill
plus the sum of all incrementals, which assumes that every full re-read after the
first was avoidable.
[15a](15a-a-trailing-system-message-rewrites-the-head.md) shows that most of them
were avoidable.

## The two kinds of optimisation this separates

- **Faster prefill.** Ubatch size and weight format. This scales all 73.4
  minutes. See [12a](12a-ubatch-2048-buys-19-to-31-percent-of-prefill.md).
- **Less prefill.** Only
  [15b](15b-inline-rendering-removes-96-percent-of-redundant-prefill.md) touches
  the 57.9 minutes of waste.

The two multiply. They do not compete.
