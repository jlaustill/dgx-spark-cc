---
id: "15d"
status: verified
title: V4's template is the outlier, and in-place rendering is the mainstream convention
measured: 2026-08-18
see_also: ["15a", "15b", "15e", "19"]
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

## Confirmed in production, 2026-08-26

The Qwen row was read off the template. It has since been served. Qwen3-Coder-Next
uses the same template family — only `messages[0]` becomes the system block, later
system messages fall through the `message.role == "user" or "system" or
"assistant"` branch and render where the client put them — and over 16 hours and
2,173 requests the **median turn re-prefilled 0.50% of its context** (p75 2.08%).

No template override was needed or passed. The prediction was that in-place
rendering makes the prompt append-only; the production distribution is what
append-only looks like. See [19](../unverified/19-removing-attention-layers-flattens-decode-decay.md)
for the run these numbers come from.
