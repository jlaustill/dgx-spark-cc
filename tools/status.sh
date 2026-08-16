#!/usr/bin/env bash
# status.sh — what is running, how far in, and how much longer.
#
# Long verification runs go quiet for tens of minutes: llama-perplexity prints
# nothing between chunks, llama-bench prints nothing until a row completes, and a
# 131k-token forward pass looks identical to a hung process. This reads whatever
# progress signal the running tool actually emits and turns it into elapsed/ETA.
#
# Signals, in order of reliability:
#   llama-server      "progress = 0.42"        -> exact fraction
#   llama-perplexity  "ETA 12.34 minutes"      -> the tool's own estimate
#                     "[3]4.1865,"             -> chunks done, if --chunks known
#   llama-bench       no progress output       -> estimate from tokens/throughput
#
#   ./status.sh              # one snapshot
#   ./status.sh -w           # refresh every 20s until idle (for a live terminal)

set -uo pipefail
V=/home/linux/verify
WATCH=${1:-}

bar() {  # bar <fraction>
  local f=$1 w=32 n
  n=$(python3 -c "print(int($f*$w))" 2>/dev/null || echo 0)
  printf '['
  printf '%0.s#' $(seq 1 $n) 2>/dev/null
  printf '%0.s.' $(seq 1 $((w-n))) 2>/dev/null
  printf '] %s%%' "$(python3 -c "print(f'{100*$f:.1f}')" 2>/dev/null || echo '?')"
}

hms() { python3 -c "
s=int($1)
print(f'{s//3600}h{(s%3600)//60:02d}m' if s>=3600 else (f'{s//60}m{s%60:02d}s' if s>=60 else f'{s}s'))" 2>/dev/null; }

snapshot() {
  local pid proc started elapsed
  pid=$(pgrep -x llama-bench || pgrep -x llama-perplexity || pgrep -x llama-server || pgrep -x ds4-server || true)
  if [[ -z ${pid:-} ]]; then
    echo "idle — no model process running"
    local mem; mem=$(free -g | awk '/^Mem:/{print $3}')
    echo "  memory in use: ${mem} GB"
    return 1
  fi
  pid=$(echo "$pid" | head -1)
  proc=$(ps -o comm= -p "$pid")
  elapsed=$(ps -o etimes= -p "$pid" | tr -d ' ')
  echo "running: $proc (pid $pid)   elapsed $(hms "$elapsed")"

  # newest log touched in the last few minutes is almost certainly the live one
  local log
  log=$(find "$V" -maxdepth 1 -name '*.log' -newermt '-10 minutes' -printf '%T@ %p\n' 2>/dev/null \
        | sort -rn | head -1 | cut -d' ' -f2-)
  [[ -z ${log:-} ]] && { echo "  (no recent log to read progress from)"; return 0; }
  echo "  log: $(basename "$log")"

  # 1. server-style exact fraction
  local frac
  frac=$(grep -aoE 'progress = [0-9.]+' "$log" 2>/dev/null | tail -1 | grep -oE '[0-9.]+' || true)
  if [[ -n ${frac:-} ]] && python3 -c "exit(0 if 0<$frac<1 else 1)" 2>/dev/null; then
    echo -n "  prefill  "; bar "$frac"
    local eta; eta=$(python3 -c "print(int($elapsed*(1-$frac)/$frac))" 2>/dev/null)
    echo "   ETA $(hms "$eta")"
    return 0
  fi

  # 2. perplexity's own ETA, plus chunks completed
  local pe chunks total
  pe=$(grep -aoE 'ETA [0-9.]+ minutes' "$log" 2>/dev/null | tail -1 | grep -oE '[0-9.]+' || true)
  chunks=$(grep -aoE '^\[[0-9]+\]' "$log" 2>/dev/null | tail -1 | tr -d '[]' || true)
  total=$(grep -aoE 'perplexity over [0-9]+ chunks' "$log" 2>/dev/null | tail -1 | grep -oE '[0-9]+' || true)
  if [[ -n ${chunks:-} && -n ${total:-} ]]; then
    echo -n "  chunks $chunks/$total  "; bar "$(python3 -c "print($chunks/$total)")"
    echo
    return 0
  fi
  if [[ -n ${pe:-} ]]; then
    echo "  tool ETA: ${pe} min (single pass, no per-chunk output until it finishes)"
    return 0
  fi

  # 3. llama-bench: no progress output at all. Say so rather than guess silently.
  if [[ $proc == llama-bench ]]; then
    local rows; rows=$(grep -ac '^| ' "$log" 2>/dev/null || echo 0)
    echo "  llama-bench emits nothing until a row completes; $rows row(s) so far"
    echo "  (a pp131072 row at ~255 t/s is ~8.5 min per repetition)"
    return 0
  fi
  echo "  model still loading (no progress markers yet)"
}

if [[ $WATCH == "-w" ]]; then
  while snapshot; do echo; sleep 20; done
else
  snapshot
fi
