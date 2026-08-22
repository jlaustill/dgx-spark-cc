---
id: "15e"
status: verified
title: gpt-oss silently drops mid-conversation system messages
measured: 2026-08-18
see_also: ["15a", "15d"]
---

# gpt-oss silently drops mid-conversation system messages

**Claim.** The gpt-oss chat template's turn loop branches on `assistant`, `tool`
and `user`, and then ends. It has no `system` branch and no `else` branch.

A mid-conversation system message matches nothing and is **silently dropped**.

## What this means

Sending Claude Code's ephemeral reminders to a gpt-oss server means the model
never sees them.

This is a **correctness failure**, not a performance one. It is equally silent.

## Relation to the V4 defect

This is a different bug from the one in
[15a](15a-a-trailing-system-message-rewrites-the-head.md). V4 renders the message
in the wrong place. gpt-oss does not render it at all.

Both defects come from the same source. The template author did not consider a
system message arriving after the conversation had started. See
[15d](15d-the-v4-template-is-the-outlier.md).
