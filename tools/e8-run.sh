#!/usr/bin/env bash
# e8-run.sh — two server arms, one rope flag different, retrieval at four depths.
#
# Arm A is the production config: no rope flags, native 262,144 ceiling.
# Arm B stretches x2 to 524,288. The scale is chosen so 524288/2 == 262144, i.e.
# the deepest position maps exactly onto the trained ceiling and nothing
# extrapolates -- the same principle that made 09c's Qwen numbers harmless.
#
# The diagnostic is A vs B at the depths BOTH can reach (131,072 and 262,144).
# Same tokens, same needles, only the position mapping differs. If B matches A
# there, the mapping is intact and 393,216/524,288 are worth believing.

set -uo pipefail
BIN=/home/linux/llama.cpp/build/bin/llama-server
M=/home/linux/models/qwen3next/Qwen3-Coder-Next-Q4_K_M.gguf
C=/tmp/claude-1000/-home-linux/56b47a86-31c4-404c-ae88-22bb23679bf1/scratchpad/ppl-corpus.txt
OUT=/home/linux/verify/e8
T=/home/linux/code/dgx-spark-cc/tools/e8-needle.py
mkdir -p "$OUT"
log() { echo "[$(date +%H:%M:%S)] $*"; }

run_arm() {  # name ctx depths... ; rope flags via $ROPE
  local name=$1 ctx=$2; shift 2
  log "=== arm $name: ctx=$ctx rope='${ROPE[*]:-none}' ==="
  "$BIN" -m "$M" --host 127.0.0.1 --port 8005 --ctx-size "$ctx" \
     -ngl 99 -fa on --jinja --parallel 1 --cache-ram 0 \
     --ubatch-size 2048 --load-mode mlock "${ROPE[@]}" \
     > "$OUT/server-$name.log" 2>&1 &
  local pid=$!
  while ! curl -sf -m 2 http://127.0.0.1:8005/health >/dev/null 2>&1; do
    kill -0 $pid 2>/dev/null || { log "  server died on load — see server-$name.log"; return 1; }
    sleep 5
  done
  log "  loaded"
  for d in "$@"; do
    python3 "$T" "$d" "$name-$d" "$C" 2>&1 | tee -a "$OUT/needle-$name.log"
  done
  kill $pid 2>/dev/null; wait $pid 2>/dev/null
  sleep 5
}

log "stopping production server"
sudo -n systemctl stop qwen3next-server.service

ROPE=()
run_arm native 262144 131072 253952

ROPE=(--rope-scaling yarn --rope-scale 2)
run_arm yarn2 524288 131072 253952 393216 516096

log "restarting production server"
sudo -n systemctl start qwen3next-server.service
log "done"
