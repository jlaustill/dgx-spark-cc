#!/usr/bin/env bash
# X1 — resident-model ratio. Read README.md first.
#
# Refuses rather than producing a plausible wrong number. Every check below
# exists because skipping it yields a result that looks fine and is not.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIN=687e778
SHA=27cd6c432c7672cb812a92f611cf3ba7bbc35928262bb1e1253ff4ee6ae35901
URL=https://huggingface.co/ggml-org/gpt-oss-20b-GGUF/resolve/main/gpt-oss-20b-MXFP4.gguf
DOWNLOAD=0; [[ "${1:-}" == "--download" ]] && DOWNLOAD=1

die(){ echo "REFUSING: $*" >&2; exit 1; }
ok(){  echo "  ok    $*"; }

# --- which machine -----------------------------------------------------------
MACHINE="${X1_MACHINE:-}"
if [[ -z $MACHINE ]]; then
  case "$(hostname)" in
    gx10*)          MACHINE=spark ;;
    *Mira*|*mira*)  MACHINE=mira ;;
    *) die "cannot infer machine from hostname '$(hostname)'. Set X1_MACHINE=spark|mira." ;;
  esac
fi
[[ $MACHINE == spark || $MACHINE == mira ]] || die "X1_MACHINE must be spark or mira, got '$MACHINE'"
echo "== X1 on '$MACHINE' ($(hostname), $(uname -m)) =="

# --- llama.cpp ---------------------------------------------------------------
LLAMA="${X1_LLAMA:-}"
if [[ -z $LLAMA ]]; then
  for c in "$HOME/llama.cpp" "$HOME/code/llama.cpp"; do [[ -d $c ]] && { LLAMA=$c; break; }; done
fi
[[ -n $LLAMA && -d $LLAMA ]] || die "no llama.cpp checkout found. Set X1_LLAMA."
BENCH="$LLAMA/build/bin/llama-bench"
[[ -x $BENCH ]] || die "$BENCH not built."
COMMIT=$(git -C "$LLAMA" rev-parse --short=7 HEAD 2>/dev/null)
[[ $COMMIT == "$PIN" ]] || die "llama.cpp is at $COMMIT, this study is pinned to $PIN.
  Every number in this repo is on $PIN; another commit is not comparable.
  Fix:  git -C $LLAMA checkout $PIN  && rebuild"
ok "llama.cpp $COMMIT (pinned)"

# --- model -------------------------------------------------------------------
MODEL="${X1_MODEL:-$HOME/models/gptoss/gpt-oss-20b-MXFP4.gguf}"
if [[ ! -f $MODEL ]]; then
  (( DOWNLOAD )) || die "model missing at $MODEL. Re-run with --download (11.27 GiB), or set X1_MODEL."
  mkdir -p "$(dirname "$MODEL")"
  echo "  .. downloading 11.27 GiB"
  wget -q --show-progress -c -O "$MODEL" "$URL" || die "download failed"
fi
echo "  .. verifying sha256 (a truncated gguf still loads and still benches)"
GOT=$(sha256sum "$MODEL" | cut -d' ' -f1)
[[ $GOT == "$SHA" ]] || die "model sha256 mismatch.
  got  $GOT
  want $SHA"
ok "model verified, $(stat -c%s "$MODEL") bytes"

# --- nothing else may be using the accelerator -------------------------------
# pgrep -x on the exact name; NEVER pgrep -f (spark NOTES.md: it matches its own shell)
if pgrep -x llama-server >/dev/null 2>&1; then
  die "a llama-server is running. It holds weights and contends for bandwidth,
  which silently depresses this measurement. Stop it, run X1, restart it.
  V7.4 did exactly this and said so in its log."
fi
ok "no llama-server running"
if command -v nvidia-smi >/dev/null 2>&1; then
  GPU=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
  CC=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | head -1)
  VRAM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1)
  USED=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)
  # GB10 has nvidia-smi but no discrete VRAM: it answers '[N/A]', not a number.
  # Record unknown rather than coerce to 0 — 0 MiB is a plausible wrong number.
  [[ $VRAM =~ ^[0-9]+$ ]] || VRAM=
  [[ $USED =~ ^[0-9]+$ ]] || USED=
  if [[ -n $VRAM ]]; then
    ok "GPU: $GPU (cc $CC, ${VRAM} MiB, ${USED:-?} MiB in use)"
  else
    ok "GPU: $GPU (cc $CC, unified memory — nvidia-smi reports no discrete VRAM)"
  fi
else
  GPU=unified; CC=na; VRAM=0
  ok "no nvidia-smi (unified-memory box); recording gpu as 'unified'"
fi

# --- bench -------------------------------------------------------------------
OUT="$HERE/results/$MACHINE.json"; mkdir -p "$HERE/results"
RAW="$HERE/results/$MACHINE.stderr.log"; : > "$RAW"
FLAGS=(-p 4096 -n 128 -d 0,16384,65536 -ngl 99 -fa on -r 3)
echo "== two INDEPENDENT launches (not -r inside one; see findings/mira/05) =="
for L in 1 2; do
  echo "  launch $L .."
  "$BENCH" -m "$MODEL" "${FLAGS[@]}" -o json > "$HERE/results/$MACHINE.launch$L.json" 2>>"$RAW"
  [[ -s "$HERE/results/$MACHINE.launch$L.json" ]] || die "launch $L produced no output; see $RAW"
done

python3 - "$OUT" "$MACHINE" "$COMMIT" "$MODEL" "$GOT" "$GPU" "$CC" "$VRAM" \
  "$HERE/results/$MACHINE.launch1.json" "$HERE/results/$MACHINE.launch2.json" <<'PYEOF'
import json, sys, platform, datetime
out, machine, commit, model, sha, gpu, cc, vram = sys.argv[1:9]
docs = [json.load(open(p)) for p in sys.argv[9:]]
def rows(d):
    r = []
    for e in d:
        n, g, dep = e.get("n_prompt", 0), e.get("n_gen", 0), e.get("n_depth", 0)
        r.append({"test": (f"pp{n}" if n else f"tg{g}") + (f" @ d{dep}" if dep else ""),
                  "t_s": e.get("avg_ts"), "stddev": e.get("stddev_ts"),
                  "n_prompt": n, "n_gen": g, "n_depth": dep,
                  "n_gpu_layers": e.get("n_gpu_layers"), "flash_attn": e.get("flash_attn")})
    return r
res = {"experiment": "X1-resident-model-ratio", "schema": 1,
       "machine": machine, "hostname": platform.node(), "arch": platform.machine(),
       "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
       "gpu": {"name": gpu, "compute_cap": cc, "vram_mib": int(vram) if vram else None},
       "llamacpp_commit": commit, "model": {"path": model, "sha256": sha},
       "bench_flags": "-p 4096 -n 128 -d 0,16384,65536 -ngl 99 -fa on -r 3",
       "launches": [{"launch": i + 1, "rows": rows(d)} for i, d in enumerate(docs)]}
# the whole point of X1: assert nothing was offloaded
bad = [r for L in res["launches"] for r in L["rows"] if (r["n_gpu_layers"] or 0) < 24]
if bad:
    sys.exit(f"not all layers on GPU (n_gpu_layers={bad[0]['n_gpu_layers']}) — X1 requires zero offload")
json.dump(res, open(out, "w"), indent=2)
print(f"\n  wrote {out}")
for L in res["launches"]:
    for r in L["rows"]:
        print(f"    launch {L['launch']}  {r['test']:>18}  {r['t_s']:10.2f} t/s")
PYEOF
rc=$?
(( rc == 0 )) || die "result writer failed (exit $rc) — no usable $OUT was produced"
echo
echo "Done. Commit results/$MACHINE.json and push, then run ./compare.py once both exist."
