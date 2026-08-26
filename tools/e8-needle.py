#!/usr/bin/env python3
"""e8-needle.py — can a stretched Qwen3-Coder-Next still USE its context?

Perplexity cannot answer this on a 121 GB box. `llama-perplexity` reserves
n_ctx * n_vocab * 4 bytes of logits: at 262,144 tokens and a 151,936 vocab that
is 148 GiB, and it dies in std::bad_alloc. 09c hit the same wall -- its
d262144-*.log files are all this crash -- which is why that finding's table stops
at 131,072.

So this measures retrieval instead, which is closer to the question anyway.
Perplexity at depth is dominated by local token statistics; what breaks when rope
positions are wrong is the ability to attend to something far away. Three needles
per haystack at ~20/50/80% depth, asked as separate turns so they share one
prefill.

Scoring is exact substring match on a code that cannot be guessed.
"""
import json, sys, time, urllib.request

BASE = "http://127.0.0.1:8005"
NEEDLES = [
    (0.20, "ARGON-7",  "4917-QX"),
    (0.50, "BOREAL-3", "8264-LM"),
    (0.80, "CYGNUS-9", "3705-TD"),
]

def post(path, body, timeout=3600):
    r = urllib.request.Request(BASE + path, json.dumps(body).encode(),
                               {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=timeout))

def ntok(text):
    return len(post("/tokenize", {"content": text})["tokens"])

def build(corpus, target):
    """Filler trimmed to `target` tokens, with the needles spliced in by depth."""
    # binary search on characters for the token target
    lo, hi = 0, len(corpus)
    while lo < hi - 256:
        mid = (lo + hi) // 2
        if ntok(corpus[:mid]) < target: lo = mid
        else: hi = mid
    filler = corpus[:lo]
    for freq, vault, code in sorted(NEEDLES, reverse=True):
        pos = int(len(filler) * freq)
        cut = filler.find("\n", pos)
        cut = pos if cut == -1 else cut
        sentence = (f"\n\nRemember this: the access code for vault {vault} "
                    f"is {code}. That code is unique to vault {vault}.\n\n")
        filler = filler[:cut] + sentence + filler[cut:]
    return filler

def ask(haystack, vault):
    body = {"model": "probe", "temperature": 0, "max_tokens": 48, "messages": [
        {"role": "user", "content": haystack +
         f"\n\nQuestion: what is the access code for vault {vault}? "
         f"Reply with only the code."}]}
    t = time.time()
    d = post("/v1/chat/completions", body)
    return d["choices"][0]["message"]["content"], time.time() - t, d.get("usage", {})

def main():
    depth = int(sys.argv[1]); label = sys.argv[2]
    corpus = open(sys.argv[3], errors="ignore").read()
    hay = build(corpus, depth)
    actual = ntok(hay)
    print(f"[{label}] haystack {actual:,} tokens (target {depth:,})", flush=True)
    hits = 0
    for _, vault, code in NEEDLES:
        try:
            ans, secs, usage = ask(hay, vault)
        except Exception as e:
            print(f"  {vault:<9} ERROR {type(e).__name__}: {e}", flush=True); continue
        ok = code.lower() in ans.lower().replace(" ", "")
        hits += ok
        print(f"  {vault:<9} {'HIT ' if ok else 'MISS'} want {code} got {ans.strip()[:40]!r}"
              f"  {secs:.0f}s  prompt={usage.get('prompt_tokens','?')}", flush=True)
    print(f"[{label}] {hits}/{len(NEEDLES)} at {actual:,} tokens", flush=True)

main()
