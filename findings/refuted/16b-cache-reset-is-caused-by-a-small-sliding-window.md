---
id: "16b"
status: refuted
title: "REFUTED: the cache reset is caused by a 128-token sliding window"
measured: 2026-08-17
replaced_by: ["16"]
---

# REFUTED: the cache reset is caused by a 128-token sliding window

**The refuted claim.** DeepSeek V4 uses sliding-window attention with a
128-token window. The window is too small to hold a usable rollback point, so the
server resets the cache to zero.

**What the source shows.** The server is never told the window size at all.
`llama_model_n_swa()` returns a hardcoded `0` for `LLM_ARCH_DEEPSEEK4`, at
`llama-model.cpp:2506-2512`.

A threshold computed from `n_swa = 0` is **stricter** than one computed from the
real 128-token window, not looser. The reset therefore cannot be blamed on the
window being small.

## What replaced it

See [16](../verified/16-a-hardcoded-return-zero-costs-29000-tokens.md). The
hardcoded return removes three things at once: the `--swa-full` workaround, a
usable reuse threshold, and the context-checkpoint fallback.

## Why this is worth keeping

The refuted explanation leads somewhere expensive. It suggests that fixing the
reset needs new compressed-cache code, which is what caused experiment E6 to be
queued and then dropped. The real diagnosis is one line and needs no new cache
code.
