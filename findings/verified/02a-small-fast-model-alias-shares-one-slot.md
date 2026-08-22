---
id: "02a"
status: verified
title: Both model ids resolve to one model on one server slot
measured: 2026-08-10
see_also: ["02b"]
---

# Both model ids resolve to one model on one server slot

**Claim.** `ANTHROPIC_SMALL_FAST_MODEL` was set to a model id that looks cheaper.
`/v1/models` shows that both ids resolve to the same model.

## Evidence

```
ids:            ['deepseek-v4-flash', 'deepseek-v4-pro']
distinct names: {'DeepSeek V4 Flash'}
```

One model, one slot, two aliases.

## Fix

Set `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`.

A single-slot server has no cheap sibling model to route background calls to.
There is only contention for the one slot.

## Limits

This finding covers the alias only. The claim that background traffic evicts the
agent's cache is separate and is not verified. See
[02b](../unverified/02b-background-traffic-evicts-the-agent-cache.md).
