---
id: "18"
status: verified
title: Seven operational traps that fail silently
measured: 2026-08-18
see_also: ["15b"]
---

# Seven operational traps that fail silently

**Claim.** Each of these seven behaviours produces a wrong result with no error
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

## 7. The DGX dashboard never applies a kernel ABI bump

It applies updates through `aptdaemon role='role-upgrade-system'`, which is a
*safe* upgrade, and a safe upgrade never installs new packages. A kernel ABI bump
(6.17.0-**1029** to 6.17.0-**1031**) needs eight brand-new packages, because the
version is part of the package name. apt reports them "kept back", the transaction
succeeds having done nothing, and the notification never clears.

Rebooting cannot help, and the tell is that `/var/run/reboot-required` does not
exist — nothing installed, so nothing asked. Same-ABI kernel patches *do* apply,
so the failure is intermittent and reads as random.

Fix: `sudo apt full-upgrade` in a real terminal, then reboot. Expect it again on
every future ABI bump.

The same panel also advertises dependency **alternatives** as if they were
updates. It offered `nvidia-firmware-580-580.159.03` while
`nvidia-firmware-580-580.173.02` was installed and matched the running driver —
an older version, presented as an upgrade — because `nvidia-kernel-common-580`
declares firmware as a long OR-list and the dashboard enumerates the unsatisfied
branches. `apt-get -s full-upgrade` correctly reported nothing to do.

Trust `apt list --upgradable`. Do not trust the panel in either direction: it
hides real kernel updates and invents fake firmware ones.
