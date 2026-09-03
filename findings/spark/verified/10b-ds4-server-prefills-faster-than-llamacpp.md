---
id: "10b"
status: verified
title: ds4-server prefills faster than llama.cpp on the same conversation
measured: 2026-08-15
see_also: ["10a", "04b"]
---

# ds4-server prefills faster than llama.cpp on the same conversation

**Claim.** Replaying one conversation against both engines, `ds4-server`
prefilled at **309.6 t/s** and llama.cpp prefilled at **263.0 t/s** at comparable
depth.

## Evidence

| engine | tokens | seconds | rate |
|---|---:|---:|---:|
| ds4-server | 114,426 | 369.9 | **309.6 t/s** |
| llama.cpp | 138,595 | 526.9 | **263.0 t/s** |

The two token counts differ because the two engines use different chat templates.
The same conversation renders to 114,426 tokens on one and 140,656 on the other,
which is a 19% gap.

## Limits

This is consistent in **direction** with the uncontrolled table in
[10a](../unverified/10a-llamacpp-beats-ds4-server-for-v4.md), so the suspected
transposition in that table is probably not a transposition.

This is still not a controlled comparison. The quant, the KV type and the
rendered token count all differ. The measured numbers are what this finding
asserts. It does not assert why the two differ.
