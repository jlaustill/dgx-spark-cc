#!/usr/bin/env bash
# phase6.sh — the ds4-server block: V1.1, V2, V3.1, V4.2, V10.
#
# V1.1 is the one the original never ran. #1 claims "25 minutes -> 1.4 seconds,
# roughly 1000x on time-to-first-token" from enabling the disk KV cache. But that
# comparison changed TWO things at once: the cache warmed *and* the turn shrank
# from 320k new tokens to 67. The ordinary in-RAM live cache produces the same
# turn-2 speedup with no disk cache at all.
#
# Only a RESTART separates them. After a restart the live cache is gone; if the
# disk cache is doing the work, a repeat of the cold prompt is fast. If it is not,
# the 1000x belongs to the live cache and #1's headline is unattributable.
#
#   arm A   no --kv-disk-dir              turn 2 fast?  -> live cache alone
#   arm C   --kv-disk-dir, cold-max >= ctx
#   arm D   arm C, then RESTART, replay the cold prompt again  <- decisive
#
# Context is 262144 rather than the 524288 the drop-in uses: the captured prompts
# top out at 152,643 tokens, and smaller loads faster. cold-max tracks it so the
# "cold-max >= ctx" fix is still what is under test.

set -uo pipefail

DS=/home/linux/ds4/ds4-server
MODEL=/home/linux/ds4/ds4flash.gguf
KVDIR=/home/linux/.ds4/server-kv
V=/home/linux/verify
PORT=8000
CTX=262144
TOOLS=/home/linux/verify/tools

log() { echo "[$(date +%H:%M:%S)] $*"; }

stop_ds4() {
  local p
  p=$(pgrep -x ds4-server) || true
  [[ -n ${p:-} ]] && { kill $p 2>/dev/null; }
  while pgrep -x ds4-server >/dev/null; do sleep 2; done
}

# $1 = log file, remaining args = extra flags
start_ds4() {
  local out=$1; shift
  stop_ds4
  setsid nohup "$DS" --cuda -m "$MODEL" --host 127.0.0.1 --port "$PORT" \
    --ctx "$CTX" --tokens "$CTX" "$@" > "$out" 2>&1 < /dev/null &
  disown
  local waited=0
  until curl -sf -m 3 -o /dev/null "http://127.0.0.1:$PORT/v1/models" 2>/dev/null; do
    pgrep -x ds4-server >/dev/null || { log "  ds4-server DIED — see $out"; tail -15 "$out"; return 1; }
    sleep 5; waited=$((waited+5))
    (( waited > 900 )) && { log "  timeout waiting for ds4-server"; return 1; }
  done
  log "  up after ${waited}s"
}

# --- V2: are the two model ids really one slot? -----------------------------
v2_alias() {
  log "V2: /v1/models alias check"
  curl -s -m 10 "http://127.0.0.1:$PORT/v1/models" > "$V/V2-models.json" 2>&1
  python3 -c "
import json
d=json.load(open('$V/V2-models.json'))
ms=d.get('data') or d.get('models') or []
print('  ids:', [m.get('id') or m.get('name') for m in ms])
print('  distinct names:', {str(m.get('name') or m.get('id')) for m in ms})
" 2>&1 | tee -a "$V/V2-alias.log"
}

# --- V3.1: just look at the checkpoint ladder -------------------------------
v31_ladder() {
  log "V3.1: checkpoint ladder on disk"
  {
    echo "files: $(find "$KVDIR" -type f | wc -l)"
    echo "total: $(du -sb "$KVDIR" | cut -f1) bytes = $(du -sh "$KVDIR" | cut -f1)"
    find "$KVDIR" -type f -printf '%10s  %p\n' | sort -n | tail -30
  } > "$V/V3.1-ladder.txt" 2>&1
  cat "$V/V3.1-ladder.txt"
}

case "${1:-all}" in
  A)
    log "=== ARM A: no --kv-disk-dir (live cache only) ==="
    start_ds4 "$V/P6-armA-server.log" || exit 1
    v2_alias
    "$TOOLS/replay.py" --tag ds4-armA --server "http://127.0.0.1:$PORT" --only 1,2,3 \
      > "$V/P6-armA-replay.log" 2>&1
    log "  replay rc=$? -> $V/P6-armA-replay.log"
    cat "$V/P6-armA-replay.log"
    ;;
  C)
    log "=== ARM C: --kv-disk-dir, cold-max >= ctx ==="
    rm -rf "${KVDIR:?}"/*
    start_ds4 "$V/P6-armC-server.log" \
      --kv-disk-dir "$KVDIR" --kv-disk-space-mb 262144 --kv-cache-cold-max-tokens "$CTX" || exit 1
    "$TOOLS/replay.py" --tag ds4-armC --server "http://127.0.0.1:$PORT" --only 1,2,3 \
      > "$V/P6-armC-replay.log" 2>&1
    log "  replay rc=$? -> $V/P6-armC-replay.log"
    cat "$V/P6-armC-replay.log"
    v31_ladder
    ;;
  D)
    log "=== ARM D: RESTART, then replay the cold prompt again (decisive) ==="
    log "  checkpoints present before restart:"
    v31_ladder | head -3
    start_ds4 "$V/P6-armD-server.log" \
      --kv-disk-dir "$KVDIR" --kv-disk-space-mb 262144 --kv-cache-cold-max-tokens "$CTX" || exit 1
    "$TOOLS/replay.py" --tag ds4-armD --server "http://127.0.0.1:$PORT" --only 1 \
      > "$V/P6-armD-replay.log" 2>&1
    log "  replay rc=$? -> $V/P6-armD-replay.log"
    cat "$V/P6-armD-replay.log"
    ;;
  all)
    "$0" A; "$0" C; "$0" D
    echo
    echo "============ V1.1 VERDICT ============"
    echo "req #1 is the cold prompt; compare its wall time across arms."
    for a in A C D; do
      echo "--- arm $a"; grep -E "^#" "$V/P6-arm$a-replay.log" 2>/dev/null || echo "  (none)"
    done
    echo "arm A vs C : does enabling the disk cache change a COLD first prefill? (expect no)"
    echo "arm C vs D : does the disk cache survive a restart? (this is the 1000x claim)"
    echo "======================================"
    ;;
  *) echo "usage: $0 A|C|D|all" >&2; exit 1 ;;
esac
