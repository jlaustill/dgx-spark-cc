#!/usr/bin/env python3
"""eval-run.py — score a model on the fail-then-pass eval set.

The document's E4 asks whether V4 Flash can *write* a fix, not just analyse one,
and notes the case study's PR exists precisely because something already produced
a plausible-looking wrong patch. So the eval measures the real pipeline: Claude
Code, driving a local model, editing a real repository with tools -- not a
disembodied "give me a diff" request. That is the workload the whole document is
about, and it is what makes the template A/B meaningful rather than academic.

Per task:
  1. git reset --hard; check out the PR's base commit    (buggy state)
  2. apply the fixture files only                        (the failing test)
  3. confirm it FAILS -- otherwise the task is broken, skip it
  4. run Claude Code against the local server with the issue text
  5. run the fixture again
  6. score: transpiles, matches .expected.*, and passes gcc + cppcheck +
     clang-tidy + MISRA -- the project's own gate, which is exactly the
     document's "compiles" AND "fixes the issue"

Step 3 runs every time, not just at build time: a task that silently starts
passing (stale artifacts, a dirty tree) would score as a free win for whatever
model is being measured.

    ./eval-run.py --tag stock --server http://127.0.0.1:8003
    ./eval-run.py --tag patched --server http://127.0.0.1:8003   # after arm.sh patched
    ./eval-run.py --compare stock patched
"""

import argparse
import json
import os
import re
import subprocess
import time

REPO = "/home/linux/code/c-next"
SLUG = "jlaustill/c-next"
OUT = "/home/linux/verify/eval-runs"


def sh(*a, cwd=REPO, timeout=1800, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run(a, cwd=cwd, capture_output=True, text=True,
                          timeout=timeout, env=e)


def clean():
    sh("git", "reset", "--hard", "-q")
    sh("git", "clean", "-qfd")


def run_fixture(cnx):
    """-> (ran, passed, failed). ran=False distinguishes a toolchain break."""
    r = sh("npm", "test", "--", cnx, "--quiet", timeout=1200)
    out = r.stdout + r.stderr
    if re.search(r"minimum Node\.js version|Cannot find module|ERR_MODULE_NOT_FOUND", out):
        return False, 0, 0, out[-2000:]
    m = re.search(r"(\d+)/(\d+) tests passed(?:, (\d+) failed)?", out)
    if not m:
        return False, 0, 0, out[-2000:]
    p, t = int(m.group(1)), int(m.group(2))
    return True, p, t - p, out[-2000:]


def issue_text(num):
    r = subprocess.run(["gh", "api", f"repos/{SLUG}/issues/{num}"],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        return None
    d = json.loads(r.stdout)
    return f"{d['title']}\n\n{d.get('body') or ''}"


PROMPT = """Fix this bug in the c-next transpiler.

{issue}

---

A failing regression test has already been added at:
    {fixture}

Run it with:
    npm test -- {fixture}

It currently fails. Change the transpiler source so it passes. Do not edit the
test fixture or its .expected.* files -- they define correct behaviour. The test
also runs gcc, cppcheck, clang-tidy and MISRA checks on the generated C, so the
output must be valid C, not merely match a string.
"""


def server_counters(log="/home/linux/verify/arm-stock.log"):
    """(turns, prefill_tokens) so far, read from the server's own log.

    Turns and prefill are the two things that make an A/B across templates fair.
    Bounding by wall-clock alone would hand the patched arm more turns for the
    same budget -- it is ~59x cheaper per diverging turn -- and then a quality
    difference could not be separated from simply having had more attempts.
    """
    try:
        txt = open(log, errors="replace").read()
    except OSError:
        return 0, 0
    turns = txt.count("launch_slot_")
    pre = sum(int(m) for m in re.findall(r"prompt eval time =\s*[\d.]+ ms /\s*(\d+) tokens", txt))
    return turns, pre


def attempt(task, server, model, timeout, log):
    """Run Claude Code against the local server. -> dict of what happened."""
    txt = issue_text(task["issue"])
    if not txt:
        return 0, "could not fetch issue"
    prompt = PROMPT.format(issue=txt[:6000], fixture=task["fixture"])
    t0 = time.time()
    t_before, p_before = server_counters(log)
    timed_out = False
    try:
        r = sh("claude", "-p", prompt,
               "--dangerously-skip-permissions",
               "--model", model,
               timeout=timeout,
               env={"ANTHROPIC_BASE_URL": server,
                    "ANTHROPIC_API_KEY": "local",
                    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                    # The server's real window; without this Claude Code assumes
                    # 200k and compacts a conversation that never needed it.
                    "CLAUDE_CODE_MAX_CONTEXT_TOKENS": "262144",
                    "API_TIMEOUT_MS": "300000"})
        tail = (r.stdout + r.stderr)[-3000:]
    except subprocess.TimeoutExpired:
        # A timeout is a result, not a crash. Recording it keeps the run going and
        # preserves how far the model got.
        timed_out = True
        tail = "TIMED OUT"
    t_after, p_after = server_counters(log)
    return {"seconds": time.time() - t0, "timed_out": timed_out, "tail": tail,
            "turns": t_after - t_before, "prefill_tokens": p_after - p_before}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag")
    ap.add_argument("--server", default="http://127.0.0.1:8003")
    ap.add_argument("--model", default="deepseek-v4-flash")
    ap.add_argument("--set", default="/home/linux/verify/eval-set.json")
    ap.add_argument("--timeout", type=int, default=5400)
    ap.add_argument("--log", default="/home/linux/verify/arm-stock.log",
                    help="server log, for turn and prefill accounting")
    ap.add_argument("--only", help="comma-separated issue numbers")
    ap.add_argument("--compare", nargs=2, metavar=("A", "B"))
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    if a.compare:
        rows = {}
        for tag in a.compare:
            with open(f"{OUT}/{tag}.json") as f:
                rows[tag] = {r["issue"]: r for r in json.load(f)}
        keys = sorted(set(rows[a.compare[0]]) & set(rows[a.compare[1]]))
        print(f"{'issue':>7} {a.compare[0]:>12} {a.compare[1]:>12}   {'delta':>8}")
        print("-" * 48)
        tot = {t: 0 for t in a.compare}
        for k in keys:
            cells = []
            for t in a.compare:
                r = rows[t][k]
                ok = r.get("solved")
                tot[t] += bool(ok)
                cells.append("PASS" if ok else "fail")
            print(f"{'#'+str(k):>7} {cells[0]:>12} {cells[1]:>12}")
        print("-" * 48)
        for t in a.compare:
            print(f"  {t}: {tot[t]}/{len(keys)} solved")
        return

    tasks = json.load(open(a.set))["accepted"]
    if a.only:
        want = {int(x) for x in a.only.split(",")}
        tasks = [t for t in tasks if t["issue"] in want]

    results = []
    for i, t in enumerate(tasks, 1):
        print(f"\n=== [{i}/{len(tasks)}] issue #{t['issue']} — {t['title'][:52]}", flush=True)
        clean()
        if sh("git", "checkout", "-q", t["base"]).returncode != 0:
            print("  SKIP: cannot check out base"); continue
        sh("git", "checkout", t["merge"], "--", *t["fixture_files"])

        ran, _, failed, _ = run_fixture(t["fixture"])
        if not ran or failed == 0:
            print(f"  SKIP: task not reproducible (ran={ran} failed={failed})")
            results.append({**t, "solved": None, "why": "not reproducible"})
            clean(); continue
        print(f"  baseline: fails as expected", flush=True)

        att = attempt(t, a.server, a.model, a.timeout, a.log)
        changed = sh("git", "status", "--porcelain").stdout.strip().splitlines()
        edited = [l for l in changed if not any(f in l for f in t["fixture_files"])]
        print(f"  {att['seconds']/60:.1f} min, {att['turns']} turns, "
              f"{att['prefill_tokens']:,} prefill tok, {len(edited)} file(s) edited"
              f"{' [TIMEOUT]' if att['timed_out'] else ''}", flush=True)

        ran, passed, failed, out = run_fixture(t["fixture"])
        solved = bool(ran and failed == 0 and passed > 0)
        print(f"  {'SOLVED' if solved else 'not solved'}"
              f" (ran={ran} passed={passed} failed={failed})", flush=True)
        results.append({**t, "solved": solved, **att,
                        "files_edited": len(edited),
                        "tail": att["tail"][-1500:], "fixture_out": out[-800:]})
        clean()
        with open(f"{OUT}/{a.tag}.json", "w") as f:
            json.dump(results, f, indent=1)

    ok = sum(1 for r in results if r.get("solved"))
    n = sum(1 for r in results if r.get("solved") is not None)
    print(f"\n=== {a.tag}: {ok}/{n} solved ===")


if __name__ == "__main__":
    main()
