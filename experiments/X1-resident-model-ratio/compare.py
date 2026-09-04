#!/usr/bin/env python3
"""X1 — print the mira/spark ratio once both results exist.

Reads results/{mira,spark}.json. Refuses to compare runs that are not
comparable: different llama.cpp commit, different model hash, different flags.
Those are the three ways to get a confident wrong answer here.
"""
import json, os, sys, statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
R = os.path.join(HERE, "results")


def load(m):
    p = os.path.join(R, f"{m}.json")
    if not os.path.exists(p):
        return None
    return json.load(open(p))


def mean_by_test(doc):
    """Mean across independent launches, per test row."""
    acc = {}
    for L in doc["launches"]:
        for r in L["rows"]:
            acc.setdefault(r["test"], []).append(r["t_s"])
    return acc


def main():
    a, b = load("mira"), load("spark")
    missing = [m for m, d in (("mira", a), ("spark", b)) if d is None]
    if missing:
        print(f"waiting on: {', '.join(missing)}")
        print(f"  run ./run.sh on {' and '.join(missing)}, commit results/<machine>.json, git pull here")
        return 1

    problems = []
    if a["llamacpp_commit"] != b["llamacpp_commit"]:
        problems.append(f"different llama.cpp commit: mira {a['llamacpp_commit']} vs spark {b['llamacpp_commit']}")
    if a["model"]["sha256"] != b["model"]["sha256"]:
        problems.append("different model file (sha256 mismatch) — not the same weights")
    if a["bench_flags"] != b["bench_flags"]:
        problems.append(f"different bench flags:\n    mira  {a['bench_flags']}\n    spark {b['bench_flags']}")
    if problems:
        for p in problems:
            print(f"REFUSING: {p}", file=sys.stderr)
        return 1

    ma, mb = mean_by_test(a), mean_by_test(b)
    print(f"X1 — gpt-oss-20b MXFP4 fully resident, llama.cpp {a['llamacpp_commit']}")
    print(f"  mira  {a['gpu']['name']} ({a['gpu']['vram_mib']} MiB)   {a['timestamp'][:10]}")
    print(f"  spark {b['gpu']['name']} ({b['gpu']['vram_mib']} MiB)   {b['timestamp'][:10]}")
    print(f"\n{'test':>18} {'mira t/s':>12} {'spark t/s':>12} {'ratio':>8}   launch spread")
    print("-" * 76)
    for t in [k for k in ma if k in mb]:
        va, vb = st.mean(ma[t]), st.mean(mb[t])
        sa = (max(ma[t]) - min(ma[t])) / va * 100 if len(ma[t]) > 1 else 0.0
        sb = (max(mb[t]) - min(mb[t])) / vb * 100 if len(mb[t]) > 1 else 0.0
        print(f"{t:>18} {va:>12.2f} {vb:>12.2f} {va/vb:>7.2f}x   mira {sa:.2f}% spark {sb:.2f}%")
    only = [t for t in ma if t not in mb] + [t for t in mb if t not in ma]
    if only:
        print(f"\n  rows present on only one machine, skipped: {', '.join(only)}")
    print("\n  ratio > 1 means mira is faster. Decode ratios are the ones that bear on the")
    print("  VRAM-upgrade decision; prefill is compute-bound and scales differently.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
