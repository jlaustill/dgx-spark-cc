#!/usr/bin/env python3
"""render.py — turn a captured request body into the tokens the model actually sees.

The finding this exists to test says it plainly: "Any cache analysis done on the
client's request body will mispredict; the rendered prompt is the only thing that
matters." Nothing in the repo rendered anything. analyze-divergence.py hashes
`json.dumps(message)`, which is why it reports REWRITE on pairs whose only
difference is a `cache_control` marker moving — metadata that never reaches the
model at all.

So: Anthropic body -> OpenAI body -> /apply-template -> /tokenize -> token ids.

The middle step is the fiddly one. llama-server's /v1/messages handler runs
`server_chat_convert_anthropic_to_oai()` (tools/server/server-chat.cpp:334) before
templating, and /apply-template does NOT do that conversion — it expects OpenAI
shape. anth_to_oai() below is a line-by-line port of that C++ function.

A port is only worth having if it is provably faithful, so `--verify` re-counts
every request through the server's own /v1/messages/count_tokens and compares.
Equal counts on every capture means the port renders what the server renders.

    ./render.py 9                       # token count + head of the rendered prompt
    ./render.py 9 --save /tmp/r9.txt    # dump the rendered prompt
    ./render.py --verify                # port fidelity check across all captures
    ./render.py 9 --template patched.jinja   # render under an override template
"""

import argparse
import json
import os
import sys
import urllib.request

DUMP_DIR = os.environ.get("RD_DIR", "/home/linux/e1-dumps")
SERVER = os.environ.get("RD_SERVER", "http://127.0.0.1:8003")
TIMEOUT = int(os.environ.get("RD_TIMEOUT", 600))


def post(path, payload):
    req = urllib.request.Request(
        SERVER + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


# --- port of server_chat_convert_anthropic_to_oai (server-chat.cpp:334) ---------

def _normalize_billing_header(text):
    """Blank the cch= stamp, which changes every request and breaks the prefix cache.

    Ported from normalize_anthropic_billing_header (server-chat.cpp:312). Note it
    is INERT on our captures: client 2.1.227 emits
    `x-anthropic-billing-header: cc_version=...; cc_entrypoint=cli;` with no cch=
    field at all, so the function returns early. Kept anyway — dropping it would
    silently diverge from the server on any client version that still sends one.
    """
    if not text.startswith("x-anthropic-billing-header:"):
        return text
    i = text.find("cch=", len("x-anthropic-billing-header:"))
    if i == -1:
        return text
    start = i + 4
    if start + 5 < len(text) and text[start + 5] == ";":
        return text[:start] + "f" * 5 + text[start + 5:]
    return text


def anth_to_oai(body):
    """Anthropic /v1/messages body -> OpenAI chat body, matching the server exactly."""
    oai = {}
    msgs = []

    system_param = body.get("system")
    if system_param is not None:
        if isinstance(system_param, str):
            content = _normalize_billing_header(system_param)
        elif isinstance(system_param, list):
            # Concatenated with NO separator — the server does `system_content +=`.
            content = "".join(
                _normalize_billing_header(b.get("text", ""))
                for b in system_param if b.get("type") == "text"
            )
        else:
            content = ""
        msgs.append({"role": "system", "content": content})

    if "messages" not in body:
        raise ValueError("'messages' is required")

    for msg in body["messages"]:
        role = msg.get("role", "")

        if "content" not in msg:
            if role == "assistant":
                continue
            msgs.append(msg)
            continue

        content = msg["content"]
        # Strings and non-arrays pass through untouched. This is the path every
        # `role: "system"` reminder takes once Claude Code has demoted it from a
        # cache_control-marked block back to a bare string.
        if not isinstance(content, list):
            msgs.append(msg)
            continue

        tool_calls, converted, tool_results = [], [], []
        reasoning = ""
        has_tool_calls = False

        for block in content:
            btype = block.get("type", "")

            if btype == "text":
                # The WHOLE block, cache_control and all — the server does not
                # strip it here, so neither may we.
                converted.append(block)
            elif btype == "thinking":
                reasoning += block.get("thinking", "")
            elif btype == "image":
                src = block.get("source", {})
                if src.get("type") == "base64":
                    url = (f"data:{src.get('media_type','image/jpeg')};"
                           f"base64,{src.get('data','')}")
                    converted.append({"type": "image_url", "image_url": {"url": url}})
                elif src.get("type") == "url":
                    converted.append({"type": "image_url",
                                      "image_url": {"url": src.get("url", "")}})
            elif btype == "tool_use":
                tool_calls.append({
                    "id": block.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": block.get("name", ""),
                        # .dump() with no indent — compact separators matter, this
                        # string lands verbatim in the prompt.
                        "arguments": json.dumps(block.get("input", {}),
                                                separators=(",", ":")),
                    },
                })
                has_tool_calls = True
            elif btype == "tool_result":
                tid = block.get("tool_use_id", "")
                rc = block.get("content")
                if isinstance(rc, str):
                    tool_results.append({"role": "tool", "tool_call_id": tid,
                                         "content": rc})
                elif isinstance(rc, list):
                    text, parts, has_images = "", [], False
                    for c in rc:
                        if c.get("type") == "text":
                            text += c.get("text", "")
                            parts.append({"type": "text", "text": c.get("text", "")})
                        elif c.get("type") == "image":
                            has_images = True
                            src = c.get("source", {})
                            if src.get("type") == "base64":
                                url = (f"data:{src.get('media_type','image/jpeg')};"
                                       f"base64,{src.get('data','')}")
                                parts.append({"type": "image_url",
                                              "image_url": {"url": url}})
                            elif src.get("type") == "url":
                                parts.append({"type": "image_url",
                                              "image_url": {"url": src.get("url", "")}})
                    # Text-only collapses to a plain string; only mixed content
                    # keeps the array form.
                    tool_results.append({"role": "tool", "tool_call_id": tid,
                                         "content": parts if has_images else text})
                else:
                    tool_results.append({"role": "tool", "tool_call_id": tid,
                                         "content": ""})

        # A message that produced nothing at all is DROPPED, not emitted empty.
        if converted or has_tool_calls or reasoning:
            new_msg = {"role": role}
            if converted:
                new_msg["content"] = converted
            elif has_tool_calls or reasoning:
                new_msg["content"] = ""
            if tool_calls:
                new_msg["tool_calls"] = tool_calls
            if reasoning:
                new_msg["reasoning_content"] = reasoning
            msgs.append(new_msg)

        msgs.extend(tool_results)

    oai["messages"] = msgs

    if isinstance(body.get("tools"), list):
        oai["tools"] = [{
            "type": "function",
            "function": {
                "name": t.get("name", ""),
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {}),
            },
        } for t in body["tools"]]

    tc = body.get("tool_choice")
    if isinstance(tc, dict):
        if tc.get("type") == "auto":
            oai["tool_choice"] = "auto"
        elif tc.get("type") in ("any", "tool"):
            oai["tool_choice"] = "required"

    if "stop_sequences" in body:
        oai["stop"] = body["stop_sequences"]
    oai["max_tokens"] = body.get("max_tokens", 4096)

    for k in ("temperature", "top_p", "top_k", "stream", "chat_template_kwargs"):
        if k in body:
            oai[k] = body[k]

    # The V4 template branches on `thinking` and `reasoning_effort`, so these
    # change the rendered head. Not optional.
    if isinstance(body.get("thinking"), dict):
        if body["thinking"].get("type") == "enabled":
            oai["thinking_budget_tokens"] = body["thinking"].get("budget_tokens", 10000)

    if isinstance(body.get("metadata"), dict):
        uid = body["metadata"].get("user_id", "")
        if uid:
            oai["__metadata_user_id"] = uid

    return oai


# --- rendering -----------------------------------------------------------------

def load(seq):
    with open(os.path.join(DUMP_DIR, f"req-{seq:05d}.json")) as f:
        return json.load(f)


def render(body, template=None):
    """-> (rendered prompt string, token ids)."""
    if template is not None:
        # Deliberately fatal. /apply-template takes its template from
        # meta->chat_params, fixed at startup — oaicompat_chat_params_parse never
        # looks at the body for one. Setting it here is silently ignored, so the
        # A/B returns two identical streams and reads as "the patch changed
        # nothing". Cost an hour once; never again.
        raise SystemExit(
            "per-request template override is NOT supported by llama-server.\n"
            "Start a second server with --chat-template-file and point RD_SERVER "
            "at it instead.")
    oai = anth_to_oai(body)
    prompt = post("/apply-template", oai)["prompt"]
    # add_special=false / parse_special=true are the server's own defaults
    # (server-context.cpp:4965). The template emits bos_token as literal text, so
    # parse_special is what turns it back into token 0 rather than 4 characters.
    tokens = post("/tokenize", {"content": prompt})["tokens"]
    return prompt, tokens


def verify_port(seqs):
    """Prove anth_to_oai() is faithful by comparing against the server's own count."""
    print(f"{'req':>5} {'ours':>9} {'count_tokens':>13} {'delta':>7}  verdict")
    print("-" * 52)
    ok = True
    for s in seqs:
        body = load(s)
        _, tokens = render(body)
        # count_tokens takes the RAW Anthropic body and runs the real pipeline.
        probe = {k: body[k] for k in ("model", "system", "messages", "tools")
                 if k in body}
        n_ref = post("/v1/messages/count_tokens", probe)["input_tokens"]
        d = len(tokens) - n_ref
        if d:
            ok = False
        print(f"{s:>5} {len(tokens):>9,} {n_ref:>13,} {d:>7}  "
              f"{'ok' if d == 0 else '** MISMATCH **'}")
    print("-" * 52)
    print("port is faithful" if ok else
          "PORT DIVERGES — do not trust any prefix arithmetic built on it")
    return ok


def main():
    global DUMP_DIR
    ap = argparse.ArgumentParser()
    ap.add_argument("seq", nargs="?", type=int)
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--template", help="path to a chat template to override with")
    ap.add_argument("--save", help="write the rendered prompt here")
    ap.add_argument("--dir", default=DUMP_DIR)
    a = ap.parse_args()

    DUMP_DIR = a.dir

    if a.verify:
        n = len([f for f in os.listdir(DUMP_DIR) if f.startswith("req-")])
        sys.exit(0 if verify_port(range(1, n + 1)) else 1)

    if a.seq is None:
        sys.exit("give a request number, or --verify")

    tmpl = open(a.template).read() if a.template else None
    prompt, tokens = render(load(a.seq), tmpl)
    print(f"req {a.seq}: {len(prompt):,} chars -> {len(tokens):,} tokens")
    if a.save:
        with open(a.save, "w") as f:
            f.write(prompt)
        print(f"saved {a.save}")
    else:
        print("--- first 400 chars ---")
        print(prompt[:400])


if __name__ == "__main__":
    main()
