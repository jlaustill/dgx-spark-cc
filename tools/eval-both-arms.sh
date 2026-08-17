#!/usr/bin/env bash
# eval-both-arms.sh — the full E7 quality A/B plus E4, unattended.
#
# Runs all 10 fail-then-pass tasks under the stock template, restarts the server
# onto the patched template, runs the same 10, then prints the comparison.
#
# WHY BOTH ARMS GET THE SAME GENEROUS TIMEOUT rather than a turn cap: this build
# of Claude Code has no --max-turns. Bounding by wall-clock alone would hand the
# patched arm more turns for the same budget (it avoids the 167s re-reads the
# smoke test showed), so a quality difference could not be separated from simply
# having had more attempts. A timeout long enough that neither arm is normally
# cut off makes turns non-binding for both. Each task records turns and prefill
# tokens regardless, so if the timeout does bind, it is visible rather than
# silently skewing the comparison.
#
# Expect 15-40 hours. Resumable: a completed arm's JSON is not recomputed.

set -uo pipefail
V=/home/linux/verify
T=$V/tools
TIMEOUT=${EVAL_TIMEOUT:-5400}     # 90 min per task

log() { echo "[$(date '+%m-%d %H:%M:%S')] $*"; }

run_arm() {          # run_arm <tag> <armname> <serverlog>
  local tag=$1 arm=$2 slog=$3
  if [[ -s $V/eval-runs/$tag.json ]] && \
     [[ $(python3 -c "import json;print(len(json.load(open('$V/eval-runs/$tag.json'))))" 2>/dev/null || echo 0) -ge 10 ]]; then
    log "SKIP $tag — already complete"
    return 0
  fi
  log "=== ARM: $tag ($arm template) ==="
  pkill -x llama-server 2>/dev/null
  while pgrep -x llama-server >/dev/null; do sleep 2; done
  "$T/arm.sh" "$arm" >/dev/null || { log "  arm.sh failed"; return 1; }
  local waited=0
  until curl -sf -m 3 -o /dev/null http://127.0.0.1:8003/health 2>/dev/null; do
    pgrep -x llama-server >/dev/null || { log "  server died"; return 1; }
    sleep 10; waited=$((waited+10))
    (( waited > 1200 )) && { log "  server never came up"; return 1; }
  done
  log "  server up after ${waited}s"
  "$T/eval-run.py" --tag "$tag" --timeout "$TIMEOUT" --log "$slog"
  log "  arm $tag finished"
}

run_arm stock   stock   "$V/arm-stock.log"
run_arm patched patched "$V/arm-patched.log"

echo
log "=== COMPARISON ==="
"$T/eval-run.py" --compare stock patched

echo
python3 - <<'PY'
import json, os
OUT = "/home/linux/verify/eval-runs"
for tag in ("stock", "patched"):
    p = f"{OUT}/{tag}.json"
    if not os.path.exists(p):
        continue
    rows = [r for r in json.load(open(p)) if r.get("solved") is not None]
    if not rows:
        continue
    solved = sum(1 for r in rows if r["solved"])
    mins   = sum(r.get("seconds", 0) for r in rows) / 60
    turns  = sum(r.get("turns", 0) for r in rows)
    pre    = sum(r.get("prefill_tokens", 0) for r in rows)
    touts  = sum(1 for r in rows if r.get("timed_out"))
    print(f"{tag:>8}: {solved}/{len(rows)} solved | {mins:6.0f} min | "
          f"{turns:4d} turns | {pre:>12,} prefill tok | {touts} timed out")
print()
print("Prefill tokens is the E7 measurement under real agentic load;")
print("solved and turns are what make the quality comparison fair.")
PY
