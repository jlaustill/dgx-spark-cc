---
id: "04b"
status: unverified
title: The 29.7 percent divergence event is unexplained
measured: 2026-08-15
see_also: ["04a", "15a"]
---

# The 29.7 percent divergence event is unexplained

**Claim.** One `ds4-server` event diverged at about 29.7% depth, at token 119,600
of 402,000.

[15a](../verified/15a-a-trailing-system-message-rewrites-the-head.md) explains a
divergence at 6.5% depth. It does not explain this one.

Either the client changed behaviour between sessions, or there are two distinct
mechanisms and only one of them is explained.

## Why this cannot be settled with the current method

Replaying the same captured requests against both engines is not a controlled
comparison. The same conversation renders to **114,426 tokens on ds4-server** and
**140,656 tokens on llama.cpp**. That is a 19% gap, and it exists because the two
engines use different chat templates.

"Identical input, two engines" is not achievable at the token level, so V4.2 was
attempted and cannot settle this.

## Completing test

Capture a `ds4-server` session and a llama.cpp session from the same client
version and the same output style. Compare the divergence depth per request
within each engine, rather than across engines.
