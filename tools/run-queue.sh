#!/usr/bin/env bash
# run-queue.sh — run the remaining verification tests unattended, one at a time.
#
# Two rules learned the hard way, both encoded here:
#
#  1. CAPTURE EVERYTHING, FILTER AFTERWARDS. A 35-minute Qwen sweep was lost to
#     `grep "^| Qwen"` — llama-bench prints the model as lowercase `qwen3moe`, so
#     the filter silently discarded every result row. Logs are written whole; the
#     summary at the end greps the saved file, which costs nothing to redo.
#
#  2. ONE GPU CONSUMER AT A TIME. Tests are sequential by construction rather than
#     chained from separate shells, which previously left two runs racing for the
#     same 121 GB.
#
#   ./run-queue.sh            # run everything not already done
#   ./run-queue.sh V6         # run one stage
#
# Each stage is skipped if its log already exists and is non-empty, so the queue
# is resumable after an interrupt.

set -uo pipefail

BIN=/home/linux/llama.cpp/build/bin
V=/home/linux/verify
QWEN=/home/linux/models/Qwen3-Coder-30B-A3B-Instruct-Q8_0.gguf
GPTOSS=/home/linux/models/e3/gpt-oss-120b-MXFP4.gguf
CORPUS=/tmp/claude-1000/-home-linux/5efca4fb-d166-4117-9e48-78d7b1921c74/scratchpad/ppl-big.txt
ONLY="${1:-all}"

log()  { echo "[$(date +%H:%M:%S)] $*"; }
done_already() { [[ -s "$1" ]] && { log "SKIP $(basename "$1") — already present"; return 0; }; return 1; }

# --- V6: decode vs depth, f16 against q8_0 KV -------------------------------
# #6 claims decode at depth is dominated by the KV read. If so, halving KV bytes
# should roughly halve the decay slope. If the slope is unchanged, the decay is
# something else and "--cache-type q8_0 is the highest-leverage flag" is
# misattributed.
run_V6() {
  for KV in f16 q8_0; do
    local out="$V/V6-qwen-$KV.log"
    done_already "$out" && continue
    log "V6: Qwen decode sweep, KV=$KV"
    timeout 5400 "$BIN/llama-bench" -m "$QWEN" \
      -p 0 -n 64 -d 0,16384,65536,131072 -fa on -ngl 99 \
      -ctk $KV -ctv $KV -r 3 -o md > "$out" 2>&1
    log "  rc=$? -> $out"
  done
}

# --- V7.3: #7's decode corollary, never measured ----------------------------
# gpt-oss (5.1B active, MXFP4, ~2.9 GB/token) should out-decode Qwen (3.3B
# active, Q8_0, ~3.5 GB/token) by ~1.21x if decode really is bytes-bound.
run_V73() {
  local out="$V/V7.3-decode-gptoss.log"
  done_already "$out" && return
  log "V7.3: gpt-oss decode at matched shallow depth"
  timeout 3600 "$BIN/llama-bench" -m "$GPTOSS" \
    -p 0 -n 64 -d 0,16384,65536 -fa on -ngl 99 -r 3 -o md > "$out" 2>&1
  log "  rc=$? -> $out"
}

# --- V9.2: do rope flags apply when the context is within training range? ----
# The trap in #9 is that llama.cpp caps n_ctx but still applies the rope flags.
# --rope-scale 2 rescales EVERY position, not just distant ones, so a 2048-token
# context detects it -- no 131k corpus needed, and the reference is well behaved.
run_V92() {
  local a="$V/V9.2-ppl-NOFLAGS.log" b="$V/V9.2-ppl-ROPE2.log"
  if ! done_already "$a"; then
    log "V9.2 arm A: reference, no rope flags"
    timeout 3600 "$BIN/llama-perplexity" -m "$GPTOSS" -ngl 99 -fa on \
      -f "$CORPUS" --chunks 16 -c 2048 < /dev/null > "$a" 2>&1
    log "  rc=$?"
  fi
  if ! done_already "$b"; then
    log "V9.2 arm B: --rope-scaling yarn --rope-scale 2"
    timeout 3600 "$BIN/llama-perplexity" -m "$GPTOSS" -ngl 99 -fa on \
      -f "$CORPUS" --chunks 16 -c 2048 --rope-scaling yarn --rope-scale 2 \
      < /dev/null > "$b" 2>&1
    log "  rc=$?"
  fi
  # Arm C is free: ask for more context than the model was trained on and read
  # the startup log for the capping warning.
  local c="$V/V9.2-cap-262144.log"
  if ! done_already "$c"; then
    log "V9.2 arm C: -c 262144 + rope flags, startup only"
    timeout 900 "$BIN/llama-perplexity" -m "$GPTOSS" -ngl 99 -fa on \
      -f "$CORPUS" --chunks 1 -c 262144 --rope-scaling yarn --rope-scale 2 \
      < /dev/null > "$c" 2>&1
    log "  rc=$?"
  fi
}

case "$ONLY" in
  V6)   run_V6 ;;
  V7.3) run_V73 ;;
  V9.2) run_V92 ;;
  all)  run_V92; run_V6; run_V73 ;;
  *) echo "unknown stage: $ONLY" >&2; exit 1 ;;
esac

echo
echo "================= SUMMARY ================="
for f in "$V"/V6-qwen-f16.log "$V"/V6-qwen-q8_0.log "$V"/V7.3-decode-gptoss.log; do
  [[ -s $f ]] || continue
  echo "--- $(basename "$f")"
  grep -E "^\|" "$f" | grep -viE "^\| *model *\||^\| *-+" || echo "  (no rows)"
done
for f in "$V"/V9.2-ppl-NOFLAGS.log "$V"/V9.2-ppl-ROPE2.log; do
  [[ -s $f ]] || continue
  echo "--- $(basename "$f"): $(grep -oE 'PPL = [0-9.]+ \+/- [0-9.]+' "$f" || echo 'no estimate')"
done
[[ -s "$V/V9.2-cap-262144.log" ]] && {
  echo "--- capping behaviour:"
  grep -aiE "capping|n_ctx_seq|n_ctx_train|freq_scale|freq_base|training context" \
    "$V/V9.2-cap-262144.log" | head -6
}
echo "==========================================="
