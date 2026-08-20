---
id: "18"
status: verified
title: Six operational traps that fail silently
measured: 2026-08-18
see_also: ["15b"]
---

# Six operational traps that fail silently

**Claim.** Each of these six behaviours produces a wrong result with no error
message. Each one cost time on this box.

## 1. `sudo` scripts fail silently through a non-interactive wrapper

The password prompt has no TTY. Run those scripts in a real terminal.

## 2. `grep` needs `--line-buffered` when following a log

Without it, a low-volume stream looks dead for minutes.

## 3. `--load-mode mlock` needs `LimitMEMLOCK=infinity`

Set it in the systemd unit.

## 4. `llama-server` binds its chat template at startup

`/apply-template` silently ignores a `chat_template` in the request body. A
per-request template A/B therefore returns two identical streams, and it reads as
"the patch changed nothing".

**A template A/B needs a second server started with `--chat-template-file`.** See
[15b](15b-inline-rendering-removes-96-percent-of-redundant-prefill.md).

## 5. `dsv4-proxy` has `Requires=dsv4-server`

Stopping the server stops the proxy. Starting the server does **not** bring the
proxy back.

## 6. "DSpark" is already taken

It is DeepSeek's own speculative draft head, which uses `markov_head` and
`confidence_head`. It has nothing to do with the DGX Spark.
