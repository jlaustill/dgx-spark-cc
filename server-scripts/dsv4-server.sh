#!/usr/bin/env bash
# dsv4-server.sh — DeepSeek V4 Flash (UD-IQ3_XXS) via llama.cpp, 1M context.
#
# The baseline this whole project has to beat. Why llama.cpp rather than
# ds4-server, which was purpose-built for this model:
#   * llama.cpp can quantize the KV cache; ds4-server cannot. At 1M that is the
#     difference between 13.5 GiB and 7.2 GiB of cache, and therefore between
#     "does not fit" and "fits".
#   * UD-IQ3_XXS is ~3.06 bpw vs the ~2.3 bpw q2 ds4-server was running, so this
#     is a quality UPGRADE, not a compression.
#   * llama.cpp implements V4's compressed attention (src/models/deepseek4.cpp:
#     INDEXER_TOP_K, COMPRESS_RATIOS, sliding window), so the ~13.5 KiB/token KV
#     that makes 1M viable at all is preserved.
#
# Budget at 1M with q8_0 KV: 95.9 weights + 7.2 KV + ~8 buffers = ~111 of 121 GiB.
# f16 KV would be ~117 and will not fit. Do not "improve" the KV type here.
#
#   ./dsv4-server.sh                    # 1M context
#   DS_CTX=524288 ./dsv4-server.sh      # 512k, more headroom
#   DS_LOAD_MODE=mmap ./dsv4-server.sh  # if mlock fails at 103 GiB

set -euo pipefail

BIN="${DS_BIN:-/home/linux/llama.cpp/build/bin/llama-server}"
# llama.cpp resolves the remaining shards automatically from part 1.
MODEL="${DS_MODEL:-/home/linux/models/dsv4/UD-IQ3_XXS/DeepSeek-V4-Flash-UD-IQ3_XXS-00001-of-00004.gguf}"
PORT="${DS_PORT:-8003}"
HOST="${DS_HOST:-0.0.0.0}"
# Model is native 1M; no rope scaling needed or wanted.
CTX="${DS_CTX:-1048576}"
KV_TYPE="${DS_KV_TYPE:-q8_0}"
LOAD_MODE="${DS_LOAD_MODE:-mlock}"
# llama.cpp defaults n_ubatch to 512, which caps arithmetic intensity. Measured
# on this exact model (llama-bench, E2): 2048 gives +41% prefill at 4k depth,
# +31% at 64k. Costs compute-buffer memory, and at 1M ctx headroom is only
# ~14 GB — drop to 512 if the server OOMs on load.
UBATCH="${DS_UBATCH:-2048}"

[[ -x $BIN ]] || { echo "error: $BIN not found — run build-llamacpp.sh" >&2; exit 1; }
[[ -f $MODEL ]] || { echo "error: model not found at $MODEL" >&2; exit 1; }

# V4's compressed attention costs ~13.5 KiB/token at f16 (measured on ds4-server:
# 7.08 GiB at 512k), roughly half that at q8_0.
PER_TOK=$([[ $KV_TYPE == f16 ]] && echo 13824 || echo 7373)
KV_GIB=$(( CTX * PER_TOK / 1073741824 ))
echo "DeepSeek-V4-Flash UD-IQ3_XXS  ctx=$CTX  kv=$KV_TYPE  ub=$UBATCH  ~96 GiB weights + ~${KV_GIB} GiB KV"

if (( CTX >= 1048576 )) && [[ $KV_TYPE == f16 ]]; then
  echo "warning: f16 KV at 1M needs ~117 GiB total and will likely OOM. Use q8_0." >&2
fi

# The single largest measured win in this project, and it is one flag.
# Claude Code appends ephemeral system-role messages to the END of the messages
# array. V4's stock template hoists every system message to the TOP of the
# rendered prompt, so a tail append lands ~9,700 tokens in (6.5% depth) and
# invalidates the 93% that follows. Rendering mid-conversation system messages
# in place makes them append-only and preserves the prefix.
#   replay:  591,519 -> 154,705 prefilled tokens; 38.8 -> 10.5 min (96.4% of
#            redundant prefill removed)
#   eval:    4/10 -> 10/10 solved, 14.3h -> 8.6h, prefill per turn 17x lower
# See findings/verified/15a..15c. DS_TEMPLATE=stock reverts to the shipped one.
TEMPLATE="${DS_TEMPLATE:-/home/linux/code/dgx-spark-cc/templates/dsv4-inline-assistant.jinja}"
TEMPLATE_ARG=()
if [[ $TEMPLATE != stock ]]; then
  [[ -f $TEMPLATE ]] || { echo "error: chat template not found at $TEMPLATE" >&2; exit 1; }
  TEMPLATE_ARG=(--chat-template-file "$TEMPLATE")
  echo "chat template: $TEMPLATE (in-place system messages)"
else
  echo "chat template: stock (system messages hoisted — expect redundant prefill)"
fi

# NOTE: --cache-reuse is deliberately absent, and cannot work here.
# llama_kv_cache_dsv4::get_can_shift() returns false unconditionally ("compressed
# row metadata uses block-derived positions"), so llama_memory_can_shift() is
# false and the server silently zeroes n_cache_reuse at startup.
exec "$BIN" \
  --model "$MODEL" \
  --alias deepseek-v4-flash \
  --host "$HOST" --port "$PORT" \
  --ctx-size "$CTX" \
  --ubatch-size "$UBATCH" \
  --n-gpu-layers 99 \
  --flash-attn on \
  --cache-type-k "$KV_TYPE" \
  --cache-type-v "$KV_TYPE" \
  --jinja \
  --parallel 1 \
  --load-mode "$LOAD_MODE" \
  --threads "$(nproc)" \
  --metrics \
  "${TEMPLATE_ARG[@]}" \
  "$@"
