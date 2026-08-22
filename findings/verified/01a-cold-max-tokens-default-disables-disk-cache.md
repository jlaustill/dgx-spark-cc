---
id: "01a"
status: verified
title: A default of 30000 silently disables the disk KV cache
measured: 2026-08-10
see_also: ["01b", "03"]
---

# A default of 30000 silently disables the disk KV cache

**Claim.** `ds4-server` can write KV checkpoints to disk. Two settings must both
be correct, and only one of them is obvious.

```
--kv-disk-dir DIR                 # off by default
--kv-cache-cold-max-tokens N      # DEFAULT 30000
```

Real coding-agent prompts on this box run 75k to 400k tokens. With the default of
30000, the server checkpoints nothing, even after the operator enables the
directory.

## Evidence

The default is confirmed in source at `ds4_kvstore.c:34` and `ds4_help.c:328`.

The symptom is 82 requests in 24 hours, 82 misses, and zero hits. Every turn
prefilled the whole conversation again.

```
live kv cache miss live=321864 prompt=325568 common=1 reason=token-mismatch
```

## Fix

Set `--kv-disk-dir`. Also set `--kv-cache-cold-max-tokens` to a value equal to or
greater than `--ctx`.

## Limits

Enabling the disk cache does not help a genuinely cold prompt. It helps only
after a server restart. See
[01b](01b-disk-kv-cache-is-worth-9-6x-on-a-cold-start.md) for the measured gain.
