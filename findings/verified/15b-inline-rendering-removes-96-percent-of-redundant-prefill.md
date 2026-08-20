---
id: "15b"
status: verified
title: In-place system-message rendering removes 96.4 percent of redundant prefill
measured: 2026-08-17
see_also: ["15a", "15c", "15d"]
---

# In-place system-message rendering removes 96.4 percent of redundant prefill

**Claim.** Render system messages that appear after the prompt preamble **in
place**, rather than hoisting them. This makes them append-only and preserves the
prefix.

`llama-server --chat-template-file` takes the override. No code change is needed.

## Evidence

Same 13 captured requests, two server arms that differ in one flag, each from a
cold cache:

| | prefilled | wall |
|---|---:|---:|
| stock template | 591,519 tok | **38.8 min** |
| patched template | 154,705 tok | **10.5 min** |

This removes **96.4% of redundant prefill**.

Excluding the cold prefill that both arms pay, redundant work drops from 452,924
tokens (30.1 min) to 16,106 tokens (1.8 min).

Per request:

- Request #8 went from 149,679 tok / 590.4 s to **1,149 tok / 7.8 s**.
- Request #9 went from 150,072 tok / 592.8 s to **396 tok / 3.7 s**.

## The template

The template is at `templates/dsv4-inline-assistant.jinja`.

It keeps the preamble hoisted until the model first speaks, so only
mid-conversation reminders move.

## The quality question

Speed alone does not justify a template change. The quality gate is measured
separately and it passes. See
[15c](15c-the-patched-template-solves-10-of-10.md).
