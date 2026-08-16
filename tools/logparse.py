#!/usr/bin/env python3
"""logparse.py — what a session actually cost, per task, from llama-server logs.

The case-study block in spark-cc-finding.md is reproduced exactly by this script,
which is the point: it sums real per-task millisecond timings rather than dividing
token counts by an average rate. Prefill rate varies 190-210 t/s with depth, so the
two methods are not interchangeable.

Reuse is the number that matters and llama-server never prints it directly. It is
recoverable, though:

    prompt_total = (n_tokens at release) - n_decoded
    reused       = prompt_total - (tokens counted in `prompt eval time`)

Run against the frozen case-study log and it prints 858,025 prefill tokens in
73.4 min, 8,280 decode in 11.1 min, 6 full re-reads — the published figures.

    ./logparse.py ~/dsv4-session-frozen-20260809.log
    ./logparse.py ~/dsv4-server.log --histogram
"""

import argparse
import re
import sys
from collections import defaultdict

RE_PE = re.compile(r"task (\d+) \| prompt eval time =\s*([\d.]+) ms /\s*(\d+) tokens")
RE_EV = re.compile(r"task (\d+) \|\s+eval time =\s*([\d.]+) ms /\s*(\d+) tokens")
RE_STOP = re.compile(r"task (\d+) \| stop processing: n_tokens = (\d+)")
RE_DEC = re.compile(r"task (\d+) \| n_decoded =\s*(\d+)")

FULL_REREAD = 20000   # the doc's threshold: ~1 minute of prefill on this box


def parse(path):
    tasks = defaultdict(dict)
    with open(path, errors="replace") as f:
        for line in f:
            m = RE_PE.search(line)
            if m:
                tasks[int(m[1])]["pe"] = (float(m[2]), int(m[3]))
                continue
            # Must come after the prompt-eval test: bare `eval time` is DECODE and
            # the two lines are one word apart. The doc calls this out as a naming
            # trap and it is an easy way to swap the two headline numbers.
            m = RE_EV.search(line)
            if m and "prompt eval" not in line:
                tasks[int(m[1])]["ev"] = (float(m[2]), int(m[3]))
                continue
            m = RE_STOP.search(line)
            if m:
                tasks[int(m[1])]["stop"] = int(m[2])
                continue
            m = RE_DEC.search(line)
            if m:
                tasks[int(m[1])]["dec"] = int(m[2])
    return tasks


def summarise(tasks, histogram=False):
    pf_tok = pf_ms = dc_tok = dc_ms = 0
    full, inc = [], []
    rows = []

    for t in sorted(tasks):
        d = tasks[t]
        if "pe" in d:
            ms, k = d["pe"]
            pf_tok += k
            pf_ms += ms
            total = d["stop"] - d.get("dec", 0) if "stop" in d else None
            reused = total - k if total else None
            rows.append((t, k, ms, total, reused))
            (full if k > FULL_REREAD else inc).append((t, k, ms))
        if "ev" in d:
            ms, k = d["ev"]
            dc_tok += k
            dc_ms += ms

    print(f"{'task':>8} {'prefilled':>10} {'prompt_tot':>11} {'reused':>10} "
          f"{'reuse%':>7} {'secs':>8} {'t/s':>7}")
    print("-" * 68)
    for t, k, ms, total, reused in rows:
        pct = f"{100*reused/total:.1f}%" if reused is not None and total else "?"
        print(f"{t:>8} {k:>10,} {(f'{total:,}' if total else '?'):>11} "
              f"{(f'{reused:,}' if reused is not None else '?'):>10} {pct:>7} "
              f"{ms/1000:>8.1f} {1000*k/ms:>7.1f}")
    print("-" * 68)

    print(f"\nPREFILL  {pf_tok:>9,} tok  {pf_ms/60000:>6.1f} min  "
          f"avg {1000*pf_tok/pf_ms:.1f} t/s" if pf_ms else "no prefill")
    if dc_ms:
        print(f"DECODE   {dc_tok:>9,} tok  {dc_ms/60000:>6.1f} min  "
              f"avg {1000*dc_tok/dc_ms:.2f} t/s")
    print(f"TOTAL model time {(pf_ms+dc_ms)/60000:.1f} min")

    if full:
        largest = max(full, key=lambda x: x[1])
        inc_tok = sum(k for _, k, _ in inc)
        # "Necessary" = one full pass over the deepest prompt, plus the genuinely
        # new tokens each later turn added. A LOWER BOUND: it assumes every full
        # re-read after the first was avoidable, which is the claim under test.
        nec = largest[1] + inc_tok
        red = pf_tok - nec
        print(f"\nfull re-reads (>{FULL_REREAD:,}): {len(full)}   incremental: {len(inc)}")
        print(f"largest single prefill: task {largest[0]}  {largest[1]:,} tok")
        print(f"necessary  {nec:>9,} tok  {100*nec/pf_tok:>5.1f}% of prefill")
        print(f"REDUNDANT  {red:>9,} tok  {100*red/pf_tok:>5.1f}% of prefill"
              f"   = {100*red/pf_tok*pf_ms/(pf_ms+dc_ms):.1f}% of total model time")

    if histogram:
        # The bimodality claim (#11) lives or dies here: prefix caching is worth
        # ~9x while the prefix holds and exactly nothing across a break, so the
        # reuse fractions should cluster at the two ends with nothing between.
        buckets = defaultdict(int)
        for _, _, _, total, reused in rows:
            if reused is None or not total:
                continue
            buckets[min(int(100 * reused / total) // 10, 9)] += 1
        print("\nreuse-fraction histogram (#11 bimodality):")
        for b in range(10):
            print(f"  {b*10:>3}-{b*10+9:>3}%  {'#' * buckets[b]}{'' if buckets[b] else '.'}"
                  f"  {buckets[b]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--histogram", action="store_true")
    a = ap.parse_args()
    for path in a.logs:
        print(f"\n{'='*68}\n{path}\n{'='*68}")
        tasks = parse(path)
        if not tasks:
            print("no task timings found")
            continue
        summarise(tasks, a.histogram)


if __name__ == "__main__":
    main()
