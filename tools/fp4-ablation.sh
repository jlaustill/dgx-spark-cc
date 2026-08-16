#!/usr/bin/env bash
# fp4-ablation.sh — V7.1: is MXFP4 fast because of tensor cores, or because it is small?
#
# #13 measures MXFP4 beating Q4_K_M by 1.19-1.43x and attributes it to the native FP4
# tensor-core path gated at mmq.cu:131. But the two formats differ in TWO ways at once:
# MXFP4 takes that path AND it is 59.0 GiB against 81.8. The document notes the size
# confound and argues it should be small. That is an argument, not a measurement — and
# #13 is the finding that cancelled the custom-quant project.
#
# The ablation: force MXFP4 down the same quantize-to-q8_1 route every other block
# format takes, change nothing else, re-run the matrix.
#
#   MXFP4 advantage collapses toward 1.0x  -> tensor cores, as claimed. #13 stands.
#   MXFP4 still wins by ~1.2-1.4x          -> misattributed. The project was cancelled
#                                             on the wrong reason; re-open it.
#
# WHY NOT just flip blackwell_mma_available(): mmq.cuh:244 uses it on the HOST to pick
# tile configs, while the __device__ selector below it uses compile-time macros. Flipping
# the shared helper desynchronises host and device tile shapes — wrong results, not a
# clean ablation. Patching the use_native_fp4 data-path flag keeps the Blackwell tiles
# and swaps only the route, which is exactly the causal question.
#
# There is no GGML_CUDA_FORCE_MMQ-style env in this build, so a patch is required.
#
#   ./fp4-ablation.sh patch     # apply, rebuild in place
#   ./fp4-ablation.sh revert    # restore pristine source, rebuild in place
#   ./fp4-ablation.sh status

set -euo pipefail

SRC=/home/linux/llama.cpp
F="$SRC/ggml/src/ggml-cuda/mmq.cu"
PIN=687e7789271ec1276e3470f158428e11a4f80b6f   # every measurement so far is on this

OLD="    const bool use_native_fp4 = blackwell_mma_available(cc) && (src0->type == GGML_TYPE_MXFP4 || src0->type == GGML_TYPE_NVFP4);"

NEW="    // V7.1 ablation: GGML_CUDA_NO_FP4=1 forces MXFP4/NVFP4 down the same
    // quantize-to-q8_1 route every other block format takes, leaving the Blackwell
    // tile configs untouched. Isolates \"fast because tensor cores\" from \"fast
    // because fewer bytes\", which are confounded in the published 1.19-1.43x.
    static const bool no_native_fp4 = getenv(\"GGML_CUDA_NO_FP4\") != nullptr;
    const bool use_native_fp4 = !no_native_fp4 && blackwell_mma_available(cc) && (src0->type == GGML_TYPE_MXFP4 || src0->type == GGML_TYPE_NVFP4);"

rebuild() {
  # NOT build-llamacpp.sh: it runs `git pull --ff-only`, which would move the checkout
  # off the pinned commit and silently invalidate every number measured so far.
  echo "== incremental rebuild (only mmq.cu changed) =="
  cmake --build "$SRC/build" --config Release -j "$(nproc)" 2>&1 | tail -5
}

check_pin() {
  local head
  head=$(git -C "$SRC" rev-parse HEAD)
  [[ $head == "$PIN" ]] || {
    echo "error: checkout is at $head, expected $PIN" >&2
    echo "       measurements are not comparable across commits; aborting." >&2
    exit 1
  }
}

case "${1:-status}" in
  patch)
    check_pin
    grep -qF "GGML_CUDA_NO_FP4" "$F" && { echo "already patched"; exit 0; }
    grep -qF "$OLD" "$F" || { echo "error: anchor line not found in $F" >&2; exit 1; }
    # Strings go via argv, not through a heredoc: $NEW contains quotes and
    # backslashes that unquoted shell interpolation would mangle silently.
    OLD="$OLD" NEW="$NEW" python3 -c '
import os, sys
p = sys.argv[1]
old, new = os.environ["OLD"], os.environ["NEW"]
s = open(p).read()
if s.count(old) != 1:
    sys.exit(f"anchor appears {s.count(old)} times, expected exactly 1")
open(p, "w").write(s.replace(old, new, 1))
' "$F"
    grep -qF "GGML_CUDA_NO_FP4" "$F" || { echo "error: patch did not apply" >&2; exit 1; }
    echo "patched $F"
    rebuild
    ;;
  revert)
    git -C "$SRC" checkout -- ggml/src/ggml-cuda/mmq.cu
    echo "reverted $F to pristine"
    rebuild
    ;;
  status)
    git -C "$SRC" rev-parse HEAD
    grep -qF "GGML_CUDA_NO_FP4" "$F" && echo "STATE: patched" || echo "STATE: pristine"
    git -C "$SRC" status --porcelain ggml/src/ggml-cuda/mmq.cu
    ;;
  *) echo "usage: $0 patch|revert|status" >&2; exit 1 ;;
esac
