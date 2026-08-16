#!/usr/bin/env python3
"""quality.py — does the E7 template change what the model says?

V15.1 proves the patched template preserves the prefix. That is a throughput result
and it is not sufficient: the document's own caveat is the honest one —

    "A system-reminder rendered inline mid-conversation may be weighted differently
     by the model than one hoisted into the system block. Needs an A/B on output
     quality, not just on throughput."

The cheap objective proxy: same model, same captured prompts, temperature 0, two
templates. Greedy decoding is deterministic, so any divergence in the output is
caused by the rendering and nothing else. No reference answers, no judge, no eval
harness — just: does it still say the same thing?

Reported per prompt:
  agree     length of the common token prefix of the two generations
  identical whether they match outright
  tools     whether the same tool calls are emitted, in the same order

Tool-call identity is the one that matters most for an agent: a paraphrase is
tolerable, a different tool call is a behaviour change.

Two 100 GB models do not fit in 121 GB, so the arms cannot run side by side. Generate
against one server, restart into the other, generate again, then compare the saved
files offline. Greedy decoding is what makes that valid: the runs are separated in
time but not in behaviour.

    ./quality.py gen  --server http://127.0.0.1:8003 --tag stock   --seqs 4,9,13
    # ... restart the server into the patched arm ...
    ./quality.py gen  --server http://127.0.0.1:8003 --tag patched --seqs 4,9,13
    ./quality.py diff --a stock --b patched
"""

import argparse
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render as R

DUMP_DIR = "/home/linux/e1-dumps"


def generate(server, body, max_tokens):
    b = dict(body)
    b["max_tokens"] = max_tokens
    b["stream"] = False
    b["temperature"] = 0.0          # greedy: the whole point is determinism
    req = urllib.request.Request(
        server + "/v1/messages",
        data=json.dumps(b).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=3600) as r:
        return json.loads(r.read())


def texts_and_tools(resp):
    """-> (visible text, tool calls, reasoning).

    Reasoning is captured, not discarded. V4 Flash spends a large and variable share
    of every response on `thinking` (276 of 517 tokens in the doc's own smoke test),
    so on a modest budget the visible text can be empty and a text-only comparison
    would report "identical" for two runs that never got as far as speaking.
    """
    text, tools, reasoning = "", [], ""
    for block in resp.get("content") or []:
        t = block.get("type")
        if t == "text":
            text += block.get("text", "")
        elif t == "thinking":
            reasoning += block.get("thinking", "")
        elif t == "tool_use":
            tools.append((block.get("name"), json.dumps(block.get("input", {}),
                                                        sort_keys=True)))
    return text, tools, reasoning


def tokens_of(server, text):
    req = urllib.request.Request(
        server + "/tokenize",
        data=json.dumps({"content": text}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["tokens"]


OUT = "/home/linux/verify/quality"


def cmd_gen(a):
    os.makedirs(OUT, exist_ok=True)
    seqs = [int(x) for x in a.seqs.split(",")]
    rows = []
    for n in seqs:
        with open(os.path.join(a.dir, f"req-{n:05d}.json")) as f:
            body = json.load(f)
        r = generate(a.server, body, a.max_tokens)
        text, tools, reasoning = texts_and_tools(r)
        rows.append({"seq": n, "text": text, "tools": tools,
                     "reasoning": reasoning,
                     "stop": r.get("stop_reason"),
                     "out_tokens": (r.get("usage") or {}).get("output_tokens")})
        print(f"#{n:>3}  text {len(text):>6}ch  think {len(reasoning):>6}ch  "
              f"{len(tools)} tool call(s)  stop={r.get('stop_reason')}", flush=True)
    path = os.path.join(OUT, f"{a.tag}.json")
    with open(path, "w") as f:
        json.dump(rows, f, indent=1)
    print(f"wrote {path}")


def cmd_diff(a):
    A = {r["seq"]: r for r in json.load(open(os.path.join(OUT, f"{a.a}.json")))}
    B = {r["seq"]: r for r in json.load(open(os.path.join(OUT, f"{a.b}.json")))}
    seqs = sorted(set(A) & set(B))

    print(f"{'req':>5} {'agree':>8} {'a_len':>7} {'b_len':>7} {'ident':>6} "
          f"{'tools=':>7}  what")
    print("-" * 66)
    ident = tools_same = 0
    for n in seqs:
        # Compare the WHOLE generation, reasoning included, in emission order.
        ta = A[n]["reasoning"] + A[n]["text"]
        tb = B[n]["reasoning"] + B[n]["text"]
        i = 0
        while i < min(len(ta), len(tb)) and ta[i] == tb[i]:
            i += 1
        st = A[n]["tools"] == B[n]["tools"]
        ident += ta == tb
        tools_same += st
        what = "identical" if ta == tb else (
            f"diverges at char {i}" + ("" if st else "  ** TOOL CALLS DIFFER **"))
        print(f"{n:>5} {i:>8} {len(ta):>7} {len(tb):>7} {str(ta == tb):>6} "
              f"{str(st):>7}  {what}")
    print("-" * 66)
    print(f"identical output: {ident}/{len(seqs)}    "
          f"same tool calls: {tools_same}/{len(seqs)}")
    print("\nA tool-call difference is a behaviour change; a paraphrase is not.")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("gen")
    g.add_argument("--server", default="http://127.0.0.1:8003")
    g.add_argument("--tag", required=True)
    g.add_argument("--seqs", required=True)
    g.add_argument("--max-tokens", type=int, default=300)
    g.add_argument("--dir", default=DUMP_DIR)

    d = sub.add_parser("diff")
    d.add_argument("--a", required=True)
    d.add_argument("--b", required=True)

    a = ap.parse_args()
    if a.cmd == "gen":
        R.DUMP_DIR = a.dir
        cmd_gen(a)
    else:
        cmd_diff(a)


if __name__ == "__main__":
    main()
