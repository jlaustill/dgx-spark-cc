---
id: "01b"
status: verified
title: The disk KV cache is worth 9.6x on a cold start
measured: 2026-08-14
supersedes: "The original claim of 1517.4s to 1.4s, described as roughly 1000x."
see_also: ["01a", "03"]
---

# The disk KV cache is worth 9.6x on a cold start

**Claim.** A disk checkpoint loads in 163 ms and removes 90% of a cold-start
prefill. The gain is 9.6x, not the 1000x originally published.

## Why the original figure was wrong

The original measurement of 1517.4 s to 1.4 s changed two variables at the same
time. The cache warmed, **and** the turn shrank from 320k new tokens to 67
tokens. The ordinary in-RAM live cache produces that turn-2 speedup on its own,
with no disk cache present.

Only a **restart** separates the two effects. A restart empties the live cache,
so anything that survives it came from disk.

## Evidence

Three arms, one replayed conversation:

| arm | config | cold prefill |
|---|---|---:|
| A | no `--kv-disk-dir` | **370.1 s** |
| C | `--kv-disk-dir`, `cold-max >= ctx`, cold start | **376.6 s** |
| D | same as C, **after a server restart** | **38.8 s** |

The server log for arm D shows the mechanism:

```
kv cache hit text tokens=104944 ... load=162.9 ms
chat ctx=104944..114426:9482  prompt done 38.459s
```

The server loaded a 104,944-token checkpoint from disk in 163 ms. Only 9,482
tokens remained to prefill.

Arm A and arm C are equal. This confirms that the disk cache does nothing on a
genuinely cold prompt, which is the correct behaviour.

## Limits

The 9.6x figure applies to this workload. The original headline was inflated by
roughly 100x by the confound described above.
