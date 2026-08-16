#!/usr/bin/env python3
"""eval-build.py — assemble a fail-then-pass eval set from closed issues.

The document names this as the gating prerequisite: "10-20 real issues with
known-good patches, scored on *compiles* and *fixes the issue*". Without it E4 is
unfalsifiable, E5 is unfalsifiable, and E7 -- a measured 96.4% win -- cannot ship.

METHOD (SWE-bench shaped). For each merged PR that closes an issue:

  1. check out the PR's BASE commit          -- the buggy state
  2. apply ONLY the PR's test files          -- not the fix
  3. run them; they must FAIL                -- proves the test captures the bug
  4. apply the PR's source changes too
  5. run again; they must PASS               -- proves the test is satisfiable

A candidate that passes at step 3 is discarded: its test does not exercise the
bug, and scoring against it would flatter any model. A candidate that fails at
step 5 is discarded too -- the harness cannot reproduce the known-good fix, so a
model failing it tells us nothing.

WHY STEP 3 MATTERS. A harness whose tests are vacuous reports high scores and
means nothing. This is the same discipline that made the template A/B
trustworthy: register the criterion before seeing the result.

SELECTION IS BLIND TO DIFFICULTY. Candidates are taken in recency order and
rejected only for mechanical reasons (test won't load on base, won't fail on
base, won't pass with the fix). Never for looking hard -- otherwise the benchmark
is tuned to whatever it is about to measure.

    ./eval-build.py --limit 30 --out eval-set.json
"""

import argparse
import json
import os
import re
import subprocess
import sys

REPO = "/home/linux/code/c-next"
SLUG = "jlaustill/c-next"
# Meta-tests of the harness itself; already failing on HEAD, nothing to do with
# compiler behaviour.
KNOWN_BAD = {"test-utils.test.ts"}


def sh(*a, cwd=REPO, timeout=900):
    return subprocess.run(a, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def gh_json(path):
    r = subprocess.run(["gh", "api", path], capture_output=True, text=True, timeout=120)
    return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else None


def is_fixture(fn):
    """A runnable regression case is a .test.cnx plus its .expected.* snapshots.

    NOT a vitest spec. This project's bug regressions are transpiler fixtures:
    scripts/test.ts finds every .test.cnx, transpiles it, diffs against
    .expected.c/.h/.cpp/.hpp, then runs gcc + cppcheck + clang-tidy + MISRA on the
    generated C. That is exactly "compiles" AND "fixes the issue", already built.

    An earlier version of this matched `.test.c` and `.test.cnx` with a vitest
    regex and handed them to vitest, which silently ran nothing and reported
    "passed" -- so every candidate was rejected as not capturing its bug.
    """
    return fn.endswith(".test.cnx") or ".expected." in fn


def run_fixture(cnx):
    """-> (ran, passed, failed). ran=False means the toolchain broke, not the code.

    Node 18 could not start the transpiler at all (yargs-parser needs >=20) and
    every fixture reported "failed". A toolchain error that resembles the result
    you are hoping for is the most dangerous kind, so it is distinguished here
    rather than counted.
    """
    r = sh("npm", "test", "--", cnx, "--quiet", timeout=900)
    out = r.stdout + r.stderr
    if re.search(r"minimum Node\.js version|Cannot find module|ERR_MODULE_NOT_FOUND", out):
        return False, 0, 0
    m = re.search(r"(\d+)/(\d+) tests passed(?:, (\d+) failed)?", out)
    if not m:
        return False, 0, 0
    passed, total = int(m.group(1)), int(m.group(2))
    return True, passed, total - passed


def clean():
    # `git checkout <sha> -- <paths>` stages as well as writes, so `git checkout -- .`
    # restores from the INDEX -- which still holds the applied files -- and the repo
    # never actually resets. Every candidate after the first then fails to check out
    # its base commit. reset --hard is what discards both.
    sh("git", "reset", "--hard", "-q")
    sh("git", "clean", "-qfd")


def candidates(limit):
    prs = gh_json(f"repos/{SLUG}/pulls?state=closed&per_page=100") or []
    out = []
    for p in prs:
        if not p.get("merged_at"):
            continue
        body = (p.get("body") or "") + " " + (p.get("title") or "")
        m = re.search(r"(?:fix(?:es|ed)?|close[sd]?|resolve[sd]?)\s+#(\d+)", body, re.I)
        if m:
            out.append({"pr": p["number"], "issue": int(m.group(1)),
                        "title": p["title"], "base": p["base"]["sha"],
                        "merge": p["merge_commit_sha"]})
        if len(out) >= limit:
            break
    return out


def evaluate(c):
    files = gh_json(f"repos/{SLUG}/pulls/{c['pr']}/files") or []
    added = [f["filename"] for f in files if f.get("status") == "added"]
    fixture_files = [f for f in added if is_fixture(f)]
    cnx = [f for f in fixture_files if f.endswith(".test.cnx")]
    src = [f["filename"] for f in files if not is_fixture(f["filename"])]
    if not cnx:
        return None, "adds no .test.cnx fixture"
    if not src:
        return None, "no source changes"
    # One fixture keeps "did it fix THIS bug" unambiguous; multi-fixture PRs
    # conflate the fix with refactoring.
    target = cnx[0]

    clean()
    if sh("git", "checkout", "-q", c["base"]).returncode != 0:
        return None, "cannot check out base commit"
    sh("git", "fetch", "-q", "origin", c["merge"])

    # step 2-3: fixture only, must fail
    if sh("git", "checkout", c["merge"], "--", *fixture_files).returncode != 0:
        clean(); return None, "could not apply fixture"
    ran, _, failed = run_fixture(target)
    if not ran:
        clean(); return None, "toolchain error on base (not a code failure)"
    if failed == 0:
        clean(); return None, "fixture PASSES on the buggy base -- does not capture the bug"

    # step 4-5: add the fix, must pass
    if sh("git", "checkout", c["merge"], "--", *src).returncode != 0:
        clean(); return None, "could not apply source changes"
    ran, passed_after, failed_after = run_fixture(target)
    clean()
    if not ran:
        return None, "toolchain error with fix applied"
    if failed_after != 0:
        return None, f"known-good fix does not make it pass ({failed_after} failing)"

    return {**c, "fixture": target, "fixture_files": fixture_files, "src": src,
            "n_src": len(src), "passes_with_fix": passed_after}, "OK"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--want", type=int, default=15)
    ap.add_argument("--out", default="/home/linux/verify/eval-set.json")
    a = ap.parse_args()

    accepted, rejected = [], []
    for c in candidates(a.limit):
        task, why = evaluate(c)
        tag = "ACCEPT" if task else "reject"
        print(f"[{tag}] PR #{c['pr']:<5} issue #{c['issue']:<5} {why:<52} {c['title'][:42]}",
              flush=True)
        (accepted if task else rejected).append(task or {**c, "why": why})
        if len(accepted) >= a.want:
            break

    with open(a.out, "w") as f:
        json.dump({"accepted": accepted, "rejected": rejected}, f, indent=1)
    print(f"\n{len(accepted)} usable / {len(accepted)+len(rejected)} examined -> {a.out}")
    if accepted:
        print("Each: test fails on the base commit, passes with the known-good fix.")


if __name__ == "__main__":
    main()
