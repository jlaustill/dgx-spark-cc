#!/usr/bin/env bash
# e8-qwen3next-rope.sh — can Qwen3-Coder-Next be stretched past its native 262,144?
#
# The need is real: the box's operator works at 320k+, and this model's native
# ceiling is 262,144. V4 Flash reached 1M and was retired for speed. If a stretch
# is safe here, the tradeoff disappears; if it is not, "V4's MLA is the only thing
# on this box that reaches 320k" becomes measured rather than assumed.
#
# Why this is not already answered by 09b/09c:
#   * 09b measured a STACK (gpt-oss ships YaRN factor 32) -> +3,281%.
#   * 09c measured Qwen3-Coder-30B, which ships none, at depths INSIDE its native
#     window -> worst case +2.39%. That is compression, not extension.
#   * Neither tested a depth BEYOND the trained limit, which is what we need.
#
# Scales are chosen so ctx/scale == 262,144 exactly, i.e. the deepest position
# maps precisely onto the trained ceiling and nothing extrapolates:
#     393,216 / 1.5 = 262,144      524,288 / 2.0 = 262,144
# The s=1.0 arm at 524,288 is the naive "just raise --ctx-size" control, which
# DOES extrapolate. That contrast is the point of the experiment.
#
# Perplexity is bit-exact deterministic, so every difference is the flag.

set -uo pipefail
B=/home/linux/llama.cpp/build/bin/llama-perplexity
M=/home/linux/models/qwen3next/Qwen3-Coder-Next-Q4_K_M.gguf
C=/tmp/claude-1000/-home-linux/56b47a86-31c4-404c-ae88-22bb23679bf1/scratchpad/ppl-corpus.txt
OUT=/home/linux/verify/e8
mkdir -p "$OUT"

# cheapest and most diagnostic first
ARMS="8192:1.0 8192:2.0 262144:1.0 262144:2.0 524288:2.0 524288:1.0 393216:1.5"

log() { echo "[$(date +%H:%M:%S)] $*"; }

log "stopping production server to free the memory pool"
sudo -n systemctl stop qwen3next-server.service

for arm in $ARMS; do
  d=${arm%%:*}; s=${arm##*:}
  f="$OUT/d${d}-s${s}.log"
  if [[ -s $f ]] && grep -q "Final estimate" "$f"; then log "skip d=$d s=$s (done)"; continue; fi
  # s=1.0 passes NO rope flags, so the vendor config is untouched rather than
  # re-asserted at its own value.
  if [[ $s == "1.0" ]]; then rope=(); else rope=(--rope-scaling yarn --rope-scale "$s"); fi
  log "d=$d s=$s"
  timeout 7200 "$B" -m "$M" -ngl 99 -fa on -f "$C" --chunks 1 -c "$d" \
    "${rope[@]}" < /dev/null > "$f" 2>&1
  log "  $(grep -oE 'PPL = [0-9.]+ \+/- [0-9.]+' "$f" || tail -2 "$f" | head -1)"
done

log "restarting production server"
sudo -n systemctl start qwen3next-server.service
log "done"
