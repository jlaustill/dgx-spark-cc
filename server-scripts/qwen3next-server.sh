#!/usr/bin/env bash
# qwen3next-server.sh — Qwen3-Coder-Next (Q4_K_M) via llama.cpp.
#
# Replaces DeepSeek V4 Flash as the box's coding model. Why this is a better fit
# for the 121 GB unified pool than V4 was:
#
#   * Weights are 45.2 GiB, not 96. That leaves ~70 GiB of headroom instead of
#     ~14, so context and compute buffers stop being a knife-edge budget.
#   * Qwen3-Next is hybrid: only every 4th layer is full attention
#     (full_attention_interval=4 -> 12 of 48 layers), the other 36 are gated
#     DeltaNet with a fixed-size recurrent state. KV is 2 kv-heads x 256 head_dim
#     x (K+V) x f16 x 12 layers = 24 KiB/token of pure KV. MEASURED total context
#     cost is higher: 33.2 KiB/token (2026-08-26, memory delta between a 64k and a
#     256k load, 6375 MiB / 196608 tokens). The extra ~9 KiB/token is ctx-scaling
#     graph/compute buffers, not KV. So full 256k costs ~8.3 GiB, not ~6.
#     f16 still fits with room to spare; do not quantize the cache to "save" memory
#     we have. Independent check: the largest observed prompt-cache entry, 6959
#     MiB, divides by 33.2 KiB to 214,619 tokens against a deepest-seen context of
#     213,208 -- 0.7% apart.
#   * Its chat template renders mid-conversation system messages IN PLACE
#     (only messages[0] is hoisted into the system block). Finding #15 -- the
#     96.4%-of-redundant-prefill bug -- is a DeepSeek V4 template artifact and
#     does NOT apply here. No template override is needed or wanted.
#
# Context is native 262144 (rope_scaling: null). Do NOT pass --rope-scaling to
# stretch it: see findings/verified on gpt-oss, where stacking YaRN silently
# corrupted positions at the ceiling (34x perplexity blow-up).
#
#   ./qwen3next-server.sh                  # 256k context
#   QN_CTX=131072 ./qwen3next-server.sh    # smaller, faster to fill
#   QN_KV_TYPE=q8_0 ./qwen3next-server.sh  # only if you actually need the GiB

set -euo pipefail

BIN="${QN_BIN:-/home/linux/llama.cpp/build/bin/llama-server}"
MODEL="${QN_MODEL:-/home/linux/models/qwen3next/Qwen3-Coder-Next-Q4_K_M.gguf}"
PORT="${QN_PORT:-8003}"
HOST="${QN_HOST:-127.0.0.1}"
CTX="${QN_CTX:-262144}"
KV_TYPE="${QN_KV_TYPE:-f16}"
LOAD_MODE="${QN_LOAD_MODE:-mlock}"
# llama.cpp defaults n_ubatch to 512, which caps arithmetic intensity on prefill.
# Measured on this box (E2, llama-bench): 2048 gave +41% prefill at 4k depth and
# +31% at 64k. Costs compute-buffer memory, which here we have in abundance.
UBATCH="${QN_UBATCH:-2048}"
# Saved-prompt-cache size. llama.cpp defaults this to 8192 MiB, which is far too
# small here: measured over 16 h of production (2,173 requests), the median
# evicted cache entry was 1688 MiB and the largest 6959 MiB, so 8 GiB held only
# ~4 deep conversations. The box runs at least two interleaved conversation
# streams against a single slot, so they thrashed: 193 evictions -> 176
# mid-session full re-prefills -> 1.73 h of 5.54 h total model time burned
# re-reading context that had already been read. 24 GiB against ~59 GiB free.
CACHE_RAM="${QN_CACHE_RAM:-24576}"

[[ -x $BIN ]] || { echo "error: $BIN not found — run build-llamacpp.sh" >&2; exit 1; }
[[ -f $MODEL ]] || { echo "error: model not found at $MODEL" >&2; exit 1; }

# f16 figure is measured end-to-end (KV + ctx-scaling buffers). The q8_0 figure
# halves only the KV half and is therefore an ESTIMATE, not a measurement.
PER_TOK=$([[ $KV_TYPE == f16 ]] && echo 34000 || echo 21712)
KV_GIB=$(( CTX * PER_TOK / 1073741824 ))
echo "Qwen3-Coder-Next Q4_K_M  ctx=$CTX  kv=$KV_TYPE  ub=$UBATCH  cache-ram=${CACHE_RAM}MiB  ~45 GiB weights + ~${KV_GIB} GiB KV"

if (( CTX > 262144 )); then
  echo "warning: ctx > 262144 exceeds max_position_embeddings and needs rope stretching — don't." >&2
fi

# --jinja is mandatory: without it llama-server ignores the model's tool-call
# template and Claude Code gets no usable function calling.
exec "$BIN" \
  --model "$MODEL" \
  --alias qwen3-coder-next \
  --host "$HOST" --port "$PORT" \
  --ctx-size "$CTX" \
  --ubatch-size "$UBATCH" \
  --n-gpu-layers 99 \
  --flash-attn on \
  --cache-type-k "$KV_TYPE" \
  --cache-type-v "$KV_TYPE" \
  --jinja \
  --parallel 1 \
  --cache-ram "$CACHE_RAM" \
  --load-mode "$LOAD_MODE" \
  --threads "$(nproc)" \
  --metrics \
  "$@"
