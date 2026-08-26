#!/usr/bin/env bash
# e8-run-deep.sh — the two arms that HTTP 400'd, now that the cap can be lifted.
#
# Requires the LLAMA_ALLOW_CTX_OVERFLOW patch (tools/patches/). Without it
# server-context.cpp:1310 caps n_ctx_slot to n_ctx_train unconditionally and both
# arms return 400 before the model sees a token.
#
# Two arms, and the contrast between them is the whole point:
#
#   yarn2  ctx 524288 --rope-scale 2 -> every position maps INSIDE the trained
#          range (524288/2 = 262144). Should work if 09c's mechanism holds.
#   naive  ctx 524288, no rope flags  -> positions 262,145+ are ones the model has
#          never seen. This is what "just raise --ctx-size" does, and it is the
#          control that shows whether the rope flag is doing any work at all.
#
# If both pass, the flag is irrelevant and the cap was the only obstacle.
# If yarn2 passes and naive fails, the flag is load-bearing and the cap was
# protecting against exactly the naive case.

set -uo pipefail
BIN=/home/linux/llama.cpp/build/bin/llama-server
M=/home/linux/models/qwen3next/Qwen3-Coder-Next-Q4_K_M.gguf
C=/tmp/claude-1000/-home-linux/56b47a86-31c4-404c-ae88-22bb23679bf1/scratchpad/ppl-corpus.txt
OUT=/home/linux/verify/e8
T=/home/linux/code/dgx-spark-cc/tools/e8-needle.py
mkdir -p "$OUT"
log() { echo "[$(date +%H:%M:%S)] $*"; }

run_arm() {
  local name=$1 ctx=$2; shift 2
  log "=== arm $name: ctx=$ctx rope='${ROPE[*]:-none}' (cap lifted) ==="
  LLAMA_ALLOW_CTX_OVERFLOW=1 "$BIN" -m "$M" --host 127.0.0.1 --port 8005 \
     --ctx-size "$ctx" -ngl 99 -fa on --jinja --parallel 1 --cache-ram 0 \
     --ubatch-size 2048 --load-mode mlock "${ROPE[@]}" \
     > "$OUT/server-$name.log" 2>&1 &
  local pid=$!
  while ! curl -sf -m 2 http://127.0.0.1:8005/health >/dev/null 2>&1; do
    kill -0 $pid 2>/dev/null || { log "  server died on load"; tail -5 "$OUT/server-$name.log"; return 1; }
    sleep 5
  done
  log "  loaded; n_ctx_slot = $(grep -oE 'n_ctx_slot = [0-9]+' "$OUT/server-$name.log" | tail -1)"
  for d in "$@"; do
    python3 "$T" "$d" "$name-$d" "$C" 2>&1 | tee -a "$OUT/needle-$name.log"
  done
  kill $pid 2>/dev/null; wait $pid 2>/dev/null
  sleep 5
}

log "stopping production server"
sudo -n systemctl stop qwen3next-server.service

ROPE=(--rope-scaling yarn --rope-scale 2)
run_arm yarn2-uncapped 524288 253952 393216 516096

ROPE=()
run_arm naive-uncapped 524288 393216 516096

log "restarting production server"
sudo -n systemctl start qwen3next-server.service
log "done"
