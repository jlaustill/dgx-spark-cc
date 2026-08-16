#!/usr/bin/env python3
"""replay.py — send the same captured conversation at a server, arm after arm.

Every cache experiment in spark-cc-finding.md was "run a session and hope a
divergence happens". That is why #15 rests on 9 opportunistic requests and #4 on a
single event: the input was never the same twice, so template, flag and engine were
never isolated.

Replaying the captured bodies fixes that. Identical input, one variable, repeatable.

`max_tokens: 1` is what makes it affordable — decode is 12 t/s and irrelevant here,
prefill is the whole question. A 13-request arm costs one cold prefill plus whatever
the cache misses, not one cold prefill plus 8,000 generated tokens.

Server-reported timings are the measurement; wall-clock is only a sanity check. Read
prefill cost from the response's `timings` block, which is the same number
`prompt eval time` prints.

    ./replay.py --tag stock                       # all 13, against :8003
    ./replay.py --tag patched --server http://127.0.0.1:8003
    ./replay.py --tag swafull --only 1,7,8,9      # just the expensive pairs
"""

import argparse
import json
import os
import sys
import time
import urllib.request

DUMP_DIR = "/home/linux/e1-dumps"
OUT_DIR = "/home/linux/verify/replays"


def post(server, path, payload, timeout):
    req = urllib.request.Request(
        server + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def replay(server, seqs, timeout):
    rows = []
    for n in seqs:
        with open(os.path.join(DUMP_DIR, f"req-{n:05d}.json")) as f:
            body = json.load(f)

        # Keep the prompt byte-identical to what was captured; change only how much
        # we ask it to generate. `thinking`/`output_config` are left alone even
        # though they look like generation knobs: the V4 template branches on
        # `thinking`, so dropping them would edit the very prompt under test.
        body["max_tokens"] = 1
        body["stream"] = False

        t0 = time.time()
        try:
            resp = post(server, "/v1/messages", body, timeout)
        except Exception as e:
            print(f"#{n:>3}  FAILED after {time.time()-t0:.1f}s: {e}", flush=True)
            rows.append({"seq": n, "error": str(e)})
            continue
        wall = time.time() - t0

        # /v1/messages returns no `timings` block (that is an OAI-compat extension),
        # but the Anthropic usage fields say exactly what we need and say it more
        # directly than the log does:
        #   input_tokens            = tokens actually prefilled this turn
        #   cache_read_input_tokens = tokens the prefix cache supplied
        # Their sum is the rendered prompt length, which is a free cross-check
        # against render.py.
        u = resp.get("usage") or {}
        new = u.get("input_tokens")
        reused = u.get("cache_read_input_tokens")
        total = (new or 0) + (reused or 0)
        rows.append({"seq": n, "new": new, "reused": reused,
                     "total": total, "wall": wall})

        pct = f"{100*reused/total:.1f}%" if total else "?"
        print(f"#{n:>3}  prefilled {new:>9,}  reused {reused:>9,} ({pct:>6})"
              f"  of {total:>9,}  wall {wall:>7.1f}s", flush=True)
    return rows


def main():
    global DUMP_DIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://127.0.0.1:8003")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--only", help="comma-separated request numbers")
    ap.add_argument("--dir", default=DUMP_DIR)
    ap.add_argument("--timeout", type=int, default=3600)
    a = ap.parse_args()

    DUMP_DIR = a.dir

    if a.only:
        seqs = [int(x) for x in a.only.split(",")]
    else:
        n = len([f for f in os.listdir(DUMP_DIR) if f.startswith("req-")])
        seqs = list(range(1, n + 1))

    print(f"replaying {len(seqs)} requests at {a.server}  tag={a.tag}\n")
    rows = replay(a.server, seqs, a.timeout)

    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{a.tag}.json")
    with open(path, "w") as f:
        json.dump({"server": a.server, "tag": a.tag, "rows": rows}, f, indent=1)

    ok = [r for r in rows if r.get("new") is not None]
    tok = sum(r["new"] for r in ok)
    wall = sum(r["wall"] for r in ok)
    reused = sum(r["reused"] or 0 for r in ok)
    print(f"\ntotal prefilled {tok:,} tok   reused {reused:,} tok"
          f"   wall {wall/60:.1f} min   ({tok/wall:.1f} t/s)")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
