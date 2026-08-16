#!/usr/bin/env python3
"""patch-template.py — build the E7 candidate template from the stock one.

The stock DeepSeek V4 template collects EVERY system message into ns.system_prompt
and emits it at the head (lines 33-67). Claude Code appends its ephemeral reminders
to the tail of `messages`, so each one lands ~9,700 tokens into the rendered prompt
and invalidates the 93% that follows. Measured, on the real captures:

    #2->#3   prefix survives    9,595 of 142,981 tokens   ( 6.7%)
    #7->#8   prefix survives    9,734 of 149,679 tokens   ( 6.5%)
    #8->#9   prefix survives    9,838 of 150,072 tokens   ( 6.6%)

The patch: hoist only the LEADING system messages — the genuine prompt preamble —
and render every later one in place, so a tail append stays a tail append.
--cutoff picks where the preamble ends; see CUTOFFS below.

Four edits, applied by exact-string replacement so the diff stays auditable:
  1. compute fu.value, the index of the first message past the preamble
  2. restrict the collection loop to system messages before it
  3. add a `system` branch to the turn loop (mirrors the `tool` branch)
  4. teach the two effective-predecessor scans that an inline system message is
     user-like — without this the following assistant turn loses its
     `<｜Assistant｜>` prefix and the transition state machine breaks

    ./patch-template.py                      # -> dsv4-inline-assistant.jinja
    ./patch-template.py --cutoff user        # -> dsv4-inline-user.jinja
    ./patch-template.py --check              # verify all edits still apply
"""

import argparse
import os
import sys

TPL = "/home/linux/verify/templates"

# --- 1 + 2: only hoist system messages that precede the first user turn ---------

OLD_COLLECT = """{#- Build system prompt from all system messages (+ optional per-message response_format). -#}
{%- set ns = namespace(system_prompt='', is_first_sp=true) -%}
{%- for message in messages -%}
  {%- if message['role'] == 'system' -%}"""

NEW_COLLECT = """{#- PATCHED (E7): the cutoff past which a system message is conversation-position
    content rather than prompt preamble. Hoisting those to the head is what destroys
    the prefix cache on every append. -#}
{%- set fu = namespace(value=-1) -%}
{%- for message in messages -%}
  {%- if fu.value < 0 and message['role'] in [CUTOFF_ROLES] -%}
    {%- set fu.value = loop.index0 -%}
  {%- endif -%}
{%- endfor -%}
{#- Build system prompt from the LEADING system messages only. -#}
{%- set ns = namespace(system_prompt='', is_first_sp=true) -%}
{%- for message in messages -%}
  {%- if message['role'] == 'system' and (fu.value < 0 or loop.index0 < fu.value) -%}"""

# --- 3: render the rest inline, exactly as a tool result is rendered ------------

OLD_TOOL_END = """    {{- '<tool_result>' + (message['content'] or '') + '</tool_result>' -}}
  {%- elif message['role'] == 'developer' -%}"""

NEW_TOOL_END = """    {{- '<tool_result>' + (message['content'] or '') + '</tool_result>' -}}
  {%- elif message['role'] == 'system' -%}
    {#- PATCHED (E7): a system message after the first user turn renders HERE, in
        the position the client put it, instead of being hoisted to the head.
        Joins the user stream like a tool result does, so it is append-only. -#}
    {%- if fu.value >= 0 and loop.index0 > fu.value -%}
      {%- if state.in_user -%}
        {{- '\\n\\n' -}}
      {%- else -%}
        {{- '<｜User｜>' -}}
        {%- set state.in_user = true -%}
      {%- endif -%}
      {{- message['content'] or '' -}}
    {%- endif -%}
  {%- elif message['role'] == 'developer' -%}"""

# --- 4: an inline system message counts as user-like for the transition ---------

OLD_EP = """          {%- set ep.is_ud = _pm['role'] in ['user', 'developer', 'tool'] -%}"""

NEW_EP = """          {%- set ep.is_ud = (_pm['role'] in ['user', 'developer', 'tool']) or (_pm['role'] == 'system' and fu.value >= 0 and ep.idx > fu.value) -%}"""

# Two cutoffs, same machinery. Which system messages count as "preamble"?
#
#   user      everything from the first user turn onward renders inline. Maximal
#             cache benefit, but it also relocates the 35 KB SessionStart hook that
#             sits at index 2 — a message that is present in EVERY request and never
#             moves, so hoisting it costs the cache nothing.
#   assistant (default) preamble runs until the model first speaks. The
#             SessionStart hook stays in the system block where it was written; only
#             the mid-conversation reminders move. Identical cache benefit, smaller
#             behaviour change, so less to defend in the quality A/B.
CUTOFFS = {
    "user":      "'user', 'developer', 'tool'",
    "assistant": "'assistant'",
}

EDITS = [
    ("hoist only leading system messages", OLD_COLLECT, NEW_COLLECT, 1),
    ("inline branch in the turn loop", OLD_TOOL_END, NEW_TOOL_END, 1),
    ("effective-predecessor scans", OLD_EP, NEW_EP, 2),
]


def build(src, cutoff):
    out = src.replace("CUTOFF_ROLES", CUTOFFS[cutoff])
    applied = []
    for name, old, new, expect in EDITS:
        new = new.replace("CUTOFF_ROLES", CUTOFFS[cutoff])
        n = out.count(old)
        if n != expect:
            sys.exit(f"edit '{name}': expected {expect} occurrence(s), found {n} — "
                     f"the stock template has changed; re-read it before patching")
        out = out.replace(old, new)
        applied.append(f"{name} ({n})")
    return out, applied


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stock", default=os.path.join(TPL, "dsv4-stock.jinja"))
    ap.add_argument("--out")
    ap.add_argument("--cutoff", choices=sorted(CUTOFFS), default="assistant",
                    help="which system messages stay hoisted as preamble")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    out_path = a.out or os.path.join(TPL, f"dsv4-inline-{a.cutoff}.jinja")

    src = open(a.stock).read()
    out, applied = build(src, a.cutoff)

    if a.check:
        for x in applied:
            print(f"  ok  {x}")
        print(f"stock {len(src):,} chars -> patched {len(out):,} chars")
        return

    with open(out_path, "w") as f:
        f.write(out)
    for x in applied:
        print(f"  applied  {x}")
    print(f"wrote {out_path}  (cutoff={a.cutoff}, {len(out):,} chars)")


if __name__ == "__main__":
    main()
