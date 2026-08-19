#!/usr/bin/env python3
"""prefix.py — how much of the previous prompt survives, in tokens, not in JSON.

Two numbers decide everything the findings argue about, and both are token-level:

  LCP  longest common PREFIX  -> what the server can reuse. Everything past it is
                                re-read, however small the actual edit was.
  LCS  longest common SUFFIX  -> whether the rest merely MOVED.

If LCP + LCS >= len(old), the whole difference is a pure insertion at LCP: every
token after it is byte-identical, just at a new position. That is exactly the case
KV shifting (--cache-reuse, llama_kv_cache_dsv4::get_can_shift) was built for, and
exactly the measurement that was never taken before E6 was dropped. If the sum
falls short, content genuinely changed and no cache tier can help.

Contrast with analyze-divergence.py, which hashes json.dumps(message) and so counts
a `cache_control` marker moving as a rewrite. Its "REWRITE 12 of 12" is an artifact.

A template A/B needs TWO servers, not two request fields: llama-server binds its
chat template at startup (--chat-template-file) and /apply-template ignores any
template in the body.

    ./prefix.py                                    # every consecutive pair
    ./prefix.py --compare http://127.0.0.1:8011    # stock vs patched  <- V15.1
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render as R


def lcp(a, b):
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def lcs(a, b, limit):
    """Longest common suffix, capped so prefix and suffix cannot overlap."""
    n = min(len(a), len(b), limit)
    i = 0
    while i < n and a[len(a) - 1 - i] == b[len(b) - 1 - i]:
        i += 1
    return i


def shift_scan(old, new, p, probe=64, max_shift=40000):
    """After the prefix breaks at p, how much of the old tail reappears verbatim?

    A whole-string common suffix is the wrong instrument here: these requests
    insert at the head AND append new turns at the tail, so the suffix is short
    for a reason that has nothing to do with whether the middle survived. That
    conflation is what makes a pure relocation look like a rewrite.

    So: take a signature n-gram of the old stream at p, find where it reappears
    in new, and extend. Returns (shift, matched) — matched == len(old) - p means
    every post-divergence token survived and only moved, which is precisely the
    case KV shifting exists to repair.
    """
    tail = old[p:]
    if not tail:
        return 0, 0
    sig = tuple(tail[:probe])
    if len(sig) < probe:
        return 0, 0
    for d in range(0, min(max_shift, len(new) - p - probe + 1)):
        if tuple(new[p + d:p + d + probe]) == sig:
            k = 0
            lim = min(len(tail), len(new) - p - d)
            while k < lim and tail[k] == new[p + d + k]:
                k += 1
            return d, k
    return None, 0


def classify(old, new):
    p = lcp(old, new)
    reread = len(new) - p
    if p == len(old):
        kind, shift, matched = "APPEND", 0, 0     # free: prefix wholly intact
    elif len(old) - p <= 8:
        # The last couple of tokens are the trailing generation prompt, which
        # necessarily changes once a new turn is appended. Not a divergence.
        kind, shift, matched = "APPEND*", 0, 0
    else:
        shift, matched = shift_scan(old, new, p)
        # "Recoverable" means the old tail survived intact at a new offset.
        if matched >= len(old) - p:
            kind = "RELOCATED"                    # shifting would recover all of it
        elif matched > 0.5 * (len(old) - p):
            kind = "PARTIAL"                      # shifting recovers most of it
        else:
            kind = "REWRITE"                      # genuinely changed
    return {
        "lcp": p, "kind": kind, "reread": reread, "shift": shift,
        "matched": matched, "tail": len(old) - p,
        "old": len(old), "new": len(new),
        "depth": p / len(new) if new else 0,
    }


CACHE = "/home/linux/verify/.token-cache"


def token_streams(seqs, server, tag):
    """Rendering 13 x 150k-token prompts is not free; cache them on disk by tag.

    `server` selects WHICH template is in play: llama-server fixes the chat
    template at startup, so a template A/B is a second server on another port
    with --chat-template-file, not a request field.
    """
    os.makedirs(CACHE, exist_ok=True)
    out = {}
    prev, R.SERVER = R.SERVER, server
    try:
        for s in seqs:
            path = os.path.join(CACHE, f"{tag}-{s:05d}.json")
            if os.path.exists(path):
                with open(path) as f:
                    out[s] = json.load(f)
            else:
                out[s] = R.render(R.load(s))[1]
                with open(path, "w") as f:
                    json.dump(out[s], f)
    finally:
        R.SERVER = prev
    return out


def report(seqs, server, label="stock", tag="stock"):
    print(f"\n=== {label} template ===")
    print(f"{'pair':>9} {'old':>9} {'new':>9} {'LCP':>9} {'depth':>7} "
          f"{'re-read':>9} {'kind':<10} {'tail':>8} {'survives':>9} shift")
    print("-" * 96)
    rows = []
    streams = token_streams(seqs, server, tag)
    for a, b in zip(seqs, seqs[1:]):
        r = classify(streams[a], streams[b])
        rows.append((a, b, r))
        surv = f"{100*r['matched']/r['tail']:.0f}%" if r["tail"] else "—"
        print(f"{f'#{a}->#{b}':>9} {r['old']:>9,} {r['new']:>9,} {r['lcp']:>9,} "
              f"{r['depth']*100:>6.1f}% {r['reread']:>9,} {r['kind']:<10} "
              f"{r['tail']:>8,} {surv:>9} {r['shift'] if r['shift'] is not None else '—'}")
    print("-" * 96)
    total = sum(r["reread"] for _, _, r in rows)
    expensive = [(a, b, r) for a, b, r in rows if r["reread"] > 20000]
    print(f"total re-read {total:,} tok over {len(rows)} pairs   "
          f"expensive (>20k): {len(expensive)}")
    return rows


def capture_set(d):
    """Sequence numbers actually present, checked against the manifest.

    Captures are numbered but not contiguous: req-00001..8 of the V15.1 set were
    overwritten in place by an unrelated session and later moved out, so
    range(1, n+1) reads files that are not there. The worse failure is quieter --
    a set that merely DIFFERS from the one a published number was measured on
    still runs and still prints a total. That is precisely how the original
    overwrite survived unnoticed until token counts stopped matching, so the
    manifest is consulted rather than trusted to be irrelevant.
    """
    seqs = sorted(int(f[4:-5]) for f in os.listdir(d)
                  if f.startswith("req-") and f.endswith(".json"))
    if not seqs:
        sys.exit(f"no req-*.json in {d}")

    mpath = os.path.join(d, "manifest.jsonl")
    if not os.path.exists(mpath):
        print(f"note: no manifest.jsonl in {d} - capture provenance unchecked\n")
        return seqs

    # The manifest is append-only, so a filename appearing twice means that file
    # was written more than once and the later write won.
    rows_by_file = {}
    for line in open(mpath):
        line = line.strip()
        if line:
            r = json.loads(line)
            rows_by_file.setdefault(r["file"], []).append(r)

    warn = []
    for s_ in seqs:
        f = "req-%05d.json" % s_
        size = os.path.getsize(os.path.join(d, f))
        rows = rows_by_file.get(f)
        if not rows:
            warn.append(f"  {f}: present on disk but absent from the manifest")
        elif not any(r["bytes"] == size for r in rows):
            have = ", ".join("{:,}".format(r["bytes"]) for r in rows)
            warn.append(f"  {f}: {size:,} bytes on disk, manifest recorded {have}")
        elif len(rows) > 1:
            warn.append(f"  {f}: captured {len(rows)} times; this content is from "
                        f"{rows[-1]['ts']}, not the first capture")

    missing = [r for f, rs in rows_by_file.items() for r in rs[:1]
               if int(f[4:-5]) not in seqs]
    if missing:
        warn.append(f"  {len(missing)} manifest entr{'y' if len(missing)==1 else 'ies'} "
                    f"have no file on disk (earliest seq {min(int(r['file'][4:-5]) for r in missing)})")

    if warn:
        print("!! capture set does not match the manifest:")
        print("\n".join(warn))
        print("!! totals from this run are NOT comparable to published numbers.\n")
    return seqs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default=R.SERVER,
                    help="server whose startup template renders the baseline")
    ap.add_argument("--compare", metavar="URL",
                    help="second server (started with --chat-template-file) to A/B")
    ap.add_argument("--dir", default=R.DUMP_DIR)
    a = ap.parse_args()
    R.DUMP_DIR = a.dir

    seqs = capture_set(R.DUMP_DIR)

    if a.compare:
        stock_rows = report(seqs, a.server, "stock", "stock")
        patch_rows = report(seqs, a.compare, f"patched ({a.compare})", "patched")

        print("\n=== verdict: does rendering system messages in place preserve the prefix? ===")
        print(f"{'pair':>9} {'stock re-read':>14} {'patched re-read':>16} {'saved':>12}")
        print("-" * 56)
        ts = tp = 0
        for (a1, b1, rs), (_, _, rp) in zip(stock_rows, patch_rows):
            ts += rs["reread"]
            tp += rp["reread"]
            print(f"{f'#{a1}->#{b1}':>9} {rs['reread']:>14,} {rp['reread']:>16,} "
                  f"{rs['reread']-rp['reread']:>12,}")
        print("-" * 56)
        print(f"{'TOTAL':>9} {ts:>14,} {tp:>16,} {ts-tp:>12,}")
        if ts:
            print(f"\nredundant prefill removed: {100*(ts-tp)/ts:.1f}%")
        return

    report(seqs, a.server, a.server, "stock")


if __name__ == "__main__":
    main()
