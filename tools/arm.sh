#!/usr/bin/env bash
# arm.sh — bring up one experiment arm of the V4 server, differing in ONE flag.
#
# The production unit runs at 1M context. These arms run at 256k deliberately:
# the captured prompts top out at 152,643 tokens, so 256k is ample, it loads
# faster, and it leaves room for --swa-full (arm C) which at 1M would not fit.
# Every arm uses the SAME context, so the comparison stays controlled.
#
#   ./arm.sh stock             # GGUF-embedded template
#   ./arm.sh patched           # templates/dsv4-inline.jinja  (E7 candidate)
#   ./arm.sh swafull           # stock template + --swa-full  (V15.4)
#
# Restarting between arms is not incidental — it guarantees a cold cache, so each
# arm's first request pays the same cold prefill and the later ones are comparable.

set -euo pipefail

ARM="${1:?usage: arm.sh stock|patched|swafull}"
PORT="${ARM_PORT:-8003}"
CTX="${ARM_CTX:-262144}"
BIN=/home/linux/llama.cpp/build/bin/llama-server
MODEL=/home/linux/models/dsv4/UD-IQ3_XXS/DeepSeek-V4-Flash-UD-IQ3_XXS-00001-of-00004.gguf
LOG="/home/linux/verify/arm-${ARM}.log"

# ARM_CUTOFF picks which E7 variant the patched arm runs; see patch-template.py.
# 'assistant' (default) keeps the SessionStart hook hoisted and moves only the
# mid-conversation reminders — same cache benefit, smaller behaviour change.
CUTOFF="${ARM_CUTOFF:-assistant}"
TPL="/home/linux/verify/templates/dsv4-inline-${CUTOFF}.jinja"

extra=()
case "$ARM" in
  stock)   ;;
  patched) [[ -f $TPL ]] || { echo "error: $TPL missing — run patch-template.py" >&2; exit 1; }
           extra+=(--chat-template-file "$TPL") ;;
  swafull) extra+=(--swa-full) ;;
  *) echo "unknown arm: $ARM" >&2; exit 1 ;;
esac

if pgrep -x llama-server >/dev/null; then
  echo "error: a llama-server is already running; stop it first" >&2
  exit 1
fi

echo "arm=$ARM  port=$PORT  ctx=$CTX  extra=${extra[*]:-none}"

# setsid, not plain &: a background child stays in the caller's process group and
# dies with it when the launching command is interrupted or times out.
setsid nohup "$BIN" \
  --model "$MODEL" \
  --alias deepseek-v4-flash \
  --host 127.0.0.1 --port "$PORT" \
  --ctx-size "$CTX" \
  --ubatch-size 2048 \
  --n-gpu-layers 99 \
  --flash-attn on \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  --jinja --parallel 1 \
  --load-mode mlock \
  --threads "$(nproc)" \
  --metrics \
  "${extra[@]}" > "$LOG" 2>&1 < /dev/null &

echo "launched, log: $LOG"
