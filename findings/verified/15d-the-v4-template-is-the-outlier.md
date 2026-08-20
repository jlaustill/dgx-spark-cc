---
id: "15d"
status: verified
title: V4's template is the outlier, and in-place rendering is the mainstream convention
measured: 2026-08-18
see_also: ["15a", "15b", "15e"]
---

# V4's template is the outlier, and in-place rendering is the mainstream convention

**Claim.** Any template that hoists system messages will destroy the prefix
cache. The population of such templates is small. Comparing the three models on
this box:

| model | `messages[0]` system | later system messages | consequence |
|---|---|---|---|
| **DeepSeek V4** | all collected into `ns.system_prompt` | **hoisted to the head** | prefix cache destroyed |
| **Qwen3-Coder** | `system_message`, rest `messages[1:]` | **rendered in place** | append-only, no problem |
| **gpt-oss** | `developer_message`, rest `messages[1:]` | **silently dropped** | content loss |

## Evidence

Qwen's turn loop renders a later system message where the client put it:

```jinja
{%- elif message.role == "user" or message.role == "system" or message.role == "assistant" %}
    {{- '<|im_start|>' + message.role + '\n' + message.content + '<|im_end|>' + '\n' }}
```

## Why this strengthens the fix

V4's template is the outlier. The patch in
[15b](15b-inline-rendering-removes-96-percent-of-redundant-prefill.md) makes V4
behave exactly as Qwen already does.

That is the strongest argument that in-place rendering is correct behaviour
rather than a workaround. It is the mainstream convention, and Qwen has no cache
problem precisely because it follows that convention.

## Limits

This is still tested on one captured session, in the "learning" output style,
with a 35 KB `SessionStart` hook.

Generality across **output styles** remains untested. What is established is
generality across **templates**.

gpt-oss has a different and separate defect. See
[15e](15e-gpt-oss-drops-mid-conversation-system-messages.md).
