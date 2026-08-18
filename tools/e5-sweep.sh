#!/usr/bin/env bash
# e5-sweep.sh — the rope-stretch tolerance threshold, per E5-PLAN.md
#
# V9.2 found that a stretch destroys output at the ceiling (34x perplexity on
# gpt-oss at 131,072) but improves it at 2,048. Two points do not locate a
# threshold, and the depth dependence means one variable is not enough. This
# sweeps both.
#
# Qwen3-Coder-30B is the model because it ships NO vendor YaRN. gpt-oss ships
# factor 32, so a stretch there stacks a second scaling on the first and cannot
# isolate the variable.
#
# Perplexity here is deterministic to four decimal places, so every difference is
# caused by the changed flag.

set -uo pipefail
B=/home/linux/llama.cpp/build/bin/llama-perplexity
M=/home/linux/models/Qwen3-Coder-30B-A3B-Instruct-Q8_0.gguf
C=/tmp/claude-1000/-home-linux/5efca4fb-d166-4117-9e48-78d7b1921c74/scratchpad/ppl-e5-big.txt
OUT=/home/linux/verify/e5
mkdir -p "$OUT"

DEPTHS="8192 32768 131072 262144"
SCALES="1.0 1.25 1.5 2.0 4.0"

log() { echo "[$(date +%H:%M:%S)] $*"; }

for d in $DEPTHS; do
  for s in $SCALES; do
    f="$OUT/d${d}-s${s}.log"
    if [[ -s $f ]] && grep -q "Final estimate" "$f"; then
      log "skip d=$d s=$s (done)"; continue
    fi
    # scale 1.0 is the native control: pass no rope flags at all, so the vendor
    # config is untouched rather than re-asserted at its own value.
    if [[ $s == "1.0" ]]; then rope=(); else rope=(--rope-scaling yarn --rope-scale "$s"); fi
    log "d=$d s=$s"
    timeout 3600 "$B" -m "$M" -ngl 99 -fa on -f "$C" --chunks 1 -c "$d" \
      "${rope[@]}" < /dev/null > "$f" 2>&1
    log "  $(grep -oE 'PPL = [0-9.]+ \+/- [0-9.]+' "$f" || echo 'no estimate — check log')"
  done
done

echo
echo "=========== E5 RESULT: perplexity by depth x stretch ==========="
python3 - <<'PY'
import re, os, glob
OUT="/home/linux/verify/e5"
depths=[8192,32768,131072,262144]; scales=["1.0","1.25","1.5","2.0","4.0"]
def ppl(d,s):
    try: t=open(f"{OUT}/d{d}-s{s}.log").read()
    except OSError: return None
    m=re.search(r"PPL = ([0-9.]+)", t)
    return float(m.group(1)) if m else None
print(f"{'depth':>8} " + "".join(f"{'x'+s:>12}" for s in scales))
print("-"*(8+12*len(scales)))
for d in depths:
    row=f"{d:>8} "
    base=ppl(d,"1.0")
    for s in scales:
        v=ppl(d,s)
        if v is None: row+=f"{'--':>12}"
        elif s=="1.0" or base is None: row+=f"{v:>12.4f}"
        else: row+=f"{v:>9.2f}x{'':>2}" if v/base>=10 else f"{v:>12.4f}"
    print(row)
print()
print("Values under x1.0 are absolute perplexity. Ratios shown where >=10x the")
print("native control at that depth. Lower is better.")
PY
