---
id: "15a"
status: verified
title: A trailing system message rewrites the head of the prompt
measured: 2026-08-16
see_also: ["04a", "11a", "15b", "15d", "16", "17"]
---

# A trailing system message rewrites the head of the prompt

**Claim.** Claude Code appends ephemeral `system`-role messages to the **end** of
the `messages` array. DeepSeek V4's chat template hoists every system message to
the **top** of the rendered prompt, at template lines 33 to 67. The template
collects them into `ns.system_prompt`, appends the tools block, and emits the
result before any turn.

Appending one short system message therefore changes the rendered prompt about
**9,700 tokens in**, which is 6.5% of the way through. It does not change it at
the end, where the client wrote it.

This one interaction is the cause of 68.6% of measured model time in the case
study. See [17](17-case-study-84-5-minutes-of-model-time.md).

## Evidence

Measured at token level on 13 captured requests, rendering each through
`/apply-template` and `/tokenize`:

| pair | common prefix | depth | re-read |
|---|---:|---:|---:|
| #2 to #3 | 9,595 | 6.7% | 133,386 |
| #7 to #8 | 9,734 | 6.5% | 139,945 |
| #8 to #9 | 9,838 | 6.6% | 140,234 |

Every request that ended in a system message re-read everything. Every request
that ended in a user message reused the cache. There were no exceptions across
all 13 requests.

## It is an insertion, not a rewrite

The content after the divergence point survives **100% verbatim**. It moves by
only 104 to 234 tokens.

## The server reuses none of it

All three requests prefilled their **entire** prompt at **0.0% reuse**, despite
an available common prefix of about 9,700 tokens. See
[16](16-a-hardcoded-return-zero-costs-29000-tokens.md) for why.

## The fix

See [15b](15b-inline-rendering-removes-96-percent-of-redundant-prefill.md).
