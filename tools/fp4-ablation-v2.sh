#!/usr/bin/env bash
# fp4-ablation-v2.sh — V7.1, done properly this time.
#
# WHAT WENT WRONG IN v1. The first attempt patched only `use_native_fp4` at
# mmq.cu:131, reasoning that flipping blackwell_mma_available() would
# desynchronise host and device tile configs. That reasoning was right, and it
# created the mirror-image fault instead: mmq.cuh:267 still selected
# ggml_cuda_mmq_get_config_blackwell() on the DEVICE, so tiles said FP4 while
# data went through q8_1. It ran 1.73x "faster" and produced nan on every
# perplexity chunk. llama-bench never checks output, so throughput alone would
# have shipped a fabricated finding.
#
# WHAT MAKES THIS ONE VALID. Host and device both derive from a single macro:
#
#   common.cuh:286   #if __CUDA_ARCH__ >= BLACKWELL && < RUBIN
#                    #  define BLACKWELL_MMA_AVAILABLE        <- device selector
#   common.cuh:360   blackwell_mma_available(cc)              <- host selector
#
# Suppressing both with one compile-time flag moves them together. Everything
# else -- target arch, SASS generation, kernels -- stays identical.
#
# WHY DISABLING IT FOR BOTH FORMATS IS THE RIGHT CONTROL. It turns off Blackwell
# MMA generally, not just the FP4 path, so both MXFP4 and Q4_K_M get slower. That
# is fine, because the question is about the RATIO between them:
#
#   ratio collapses toward 1.0  -> the advantage was the native path (#13 stands)
#   ratio holds at ~1.2-1.4x    -> the advantage is bytes and unpack cost, and
#                                  #13's attribution is wrong
#
# The ratio cancels any uniform slowdown; that is what makes the comparison work.
#
# NON-NEGOTIABLE: perplexity gate before any throughput number is believed.
#
#   ./fp4-ablation-v2.sh build    # patch + build into build-noblackwell/
#   ./fp4-ablation-v2.sh gate     # perplexity must match the pristine build
#   ./fp4-ablation-v2.sh bench    # only run after the gate passes

set -uo pipefail
SRC=/home/linux/llama.cpp
BUILD=$SRC/build-noblackwell
V=/home/linux/verify
MX=/home/linux/models/e3/gpt-oss-120b-MXFP4.gguf
Q4=/home/linux/models/e3/gpt-oss-120b-Q4_K_M.gguf
CORPUS=/tmp/claude-1000/-home-linux/5efca4fb-d166-4117-9e48-78d7b1921c74/scratchpad/ppl-big.txt
PIN=687e7789271ec1276e3470f158428e11a4f80b6f

log() { echo "[$(date +%H:%M:%S)] $*"; }

case "${1:-}" in
build)
  [[ $(git -C "$SRC" rev-parse HEAD) == "$PIN" ]] || { echo "checkout moved off $PIN" >&2; exit 1; }
  # A separate build tree: the pristine build stays intact and comparable.
  log "configuring build-noblackwell (sm_121, Blackwell MMA suppressed)"
  cmake -S "$SRC" -B "$BUILD" \
    -DCMAKE_BUILD_TYPE=Release -DGGML_CUDA=ON \
    -DCMAKE_CUDA_ARCHITECTURES=121 -DGGML_NATIVE=ON -DLLAMA_CURL=OFF \
    -DCMAKE_CUDA_FLAGS="-DGGML_NO_BLACKWELL_MMA" > "$V/V7.1v2-configure.log" 2>&1
  log "  configure rc=$?"
  log "building (this takes a while)"
  cmake --build "$BUILD" --target llama-bench llama-perplexity -j "$(nproc)" \
    > "$V/V7.1v2-build.log" 2>&1
  log "  build rc=$? -> $BUILD/bin"
  ls -la "$BUILD/bin/llama-bench" "$BUILD/bin/llama-perplexity" 2>&1 | tail -2
  ;;
gate)
  log "PERPLEXITY GATE — ablated build must match the pristine build"
  for m in "$MX" "$Q4"; do
    n=$(basename "$m" .gguf)
    for b in "$SRC/build" "$BUILD"; do
      tag=$([[ $b == "$BUILD" ]] && echo ablated || echo pristine)
      out="$V/V7.1v2-ppl-$n-$tag.log"
      [[ -s $out ]] && { log "  skip $n/$tag"; continue; }
      log "  $n / $tag"
      timeout 3600 "$b/bin/llama-perplexity" -m "$m" -ngl 99 -fa on \
        -f "$CORPUS" --chunks 8 -c 2048 < /dev/null > "$out" 2>&1
    done
  done
  echo
  echo "=========== GATE ==========="
  for n in gpt-oss-120b-MXFP4 gpt-oss-120b-Q4_K_M; do
    p=$(grep -oE 'PPL = [0-9.]+' "$V/V7.1v2-ppl-$n-pristine.log" 2>/dev/null)
    a=$(grep -oE 'PPL = [0-9.]+' "$V/V7.1v2-ppl-$n-ablated.log" 2>/dev/null)
    printf '%-24s pristine: %-14s ablated: %-14s\n' "$n" "${p:-MISSING}" "${a:-MISSING}"
    [[ -n $p && "$p" == "$a" ]] && echo "    MATCH — arithmetic preserved" \
       || echo "    ** MISMATCH or nan — the ablation is invalid, do NOT bench **"
  done
  echo "============================"
  ;;
bench)
  log "matrix on the ablated build"
  for m in "$MX" "$Q4"; do
    n=$(basename "$m" .gguf)
    timeout 5400 "$BUILD/bin/llama-bench" -m "$m" -p 4096,65536 -n 0 \
      -ngl 99 -fa on -ub 512,2048 -r 3 -o md > "$V/V7.1v2-bench-$n.log" 2>&1
    log "  $n rc=$?"
  done
  echo "=========== RATIOS ==========="
  echo "compare against the pristine build (data/bench/V8-V12-V13-bench.log):"
  echo "  pristine MXFP4/Q4_K_M was 1.30-1.47x"
  grep -hE "^\| gpt" "$V"/V7.1v2-bench-*.log
  ;;
*) echo "usage: $0 build|gate|bench" >&2; exit 1 ;;
esac
