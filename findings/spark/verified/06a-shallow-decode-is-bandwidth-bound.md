---
id: "06a"
status: verified
title: Shallow decode is bandwidth-bound on weights
measured: 2026-08-12
see_also: ["00", "06c"]
---

# Shallow decode is bandwidth-bound on weights

**Claim.** At shallow depth, decode speed is set by how fast the box can read the
model weights.

## Evidence

Qwen3-Coder-30B-A3B Q8_0, three repetitions:

| depth | f16 KV | q8_0 KV |
|---:|---:|---:|
| 0 | 63.34 t/s | 61.70 t/s |
| 16,384 | 41.86 | 41.43 |
| 65,536 | 20.21 | 20.65 |
| 131,072 | **12.13** | **12.12** |

At depth 0, the arithmetic confirms the bound:

63.34 t/s x (3.3B active x 1.06 B/param) = **221 GB/s** effective.

That matches the ~227 GB/s figure measured elsewhere on this box.

## Limits

This claim covers shallow decode only. Decode slows by a factor of about 5 from
depth 0 to depth 131,072, and that decay has a different cause. The KV read does
not explain it. See
[06b](../refuted/06b-q8-0-kv-speeds-up-long-context-decode.md).
