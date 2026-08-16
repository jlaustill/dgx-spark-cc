#!/usr/bin/env bash
# heartbeat.sh — emit one progress line every few minutes for a running test.
#
# Designed to be driven by the Monitor tool: every stdout line becomes a chat
# notification, so a long quiet run reports itself instead of looking hung.
# llama-perplexity prints nothing between chunks and llama-bench prints nothing
# until a row completes, so a 35-minute run is indistinguishable from a crash.
#
# Coverage matters more than tidiness here: this emits on progress, on abnormal
# exit, AND on a stalled log, because a monitor that only reports the happy path
# stays silent through exactly the failures worth knowing about.
#
#   ./heartbeat.sh [interval_seconds] [stall_seconds]
#
# Exits 0 when no model process remains, which ends the watch.

set -uo pipefail
INTERVAL=${1:-300}
STALL=${2:-900}
V=/home/linux/verify

hms() { python3 -c "
s=int($1); print(f'{s//3600}h{(s%3600)//60:02d}m' if s>=3600 else f'{s//60}m{s%60:02d}s')" 2>/dev/null; }

live_pid() { pgrep -x llama-bench || pgrep -x llama-perplexity || pgrep -x llama-server || pgrep -x ds4-server || true; }

start=$(date +%s)
last_log_size=0
[[ -z $(live_pid) ]] && { echo "nothing running — no test to watch"; exit 0; }

while true; do
  pid=$(live_pid | head -1)
  if [[ -z ${pid:-} ]]; then
    echo "COMPLETE — no model process running after $(hms $(( $(date +%s) - start )))"
    exit 0
  fi

  proc=$(ps -o comm= -p "$pid" 2>/dev/null | tr -d ' ')
  el=$(ps -o etimes= -p "$pid" 2>/dev/null | tr -d ' ')
  [[ -z ${el:-} ]] && { echo "process vanished mid-check — likely crashed or was killed"; exit 0; }

  log=$(find "$V" -maxdepth 1 -name '*.log' -newermt '-20 minutes' -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)
  msg="$proc  elapsed $(hms "$el")"

  if [[ -n ${log:-} ]]; then
    # exact fraction if the server prints one
    frac=$(grep -aoE 'progress = [0-9.]+' "$log" 2>/dev/null | tail -1 | grep -oE '[0-9.]+' || true)
    if [[ -n ${frac:-} ]] && python3 -c "exit(0 if 0<$frac<1 else 1)" 2>/dev/null; then
      eta=$(python3 -c "print(int($el*(1-$frac)/$frac))")
      msg="$msg  $(python3 -c "print(f'{100*$frac:.0f}')")%  ETA $(hms "$eta")"
    else
      done_c=$(grep -aoE '^\[[0-9]+\]' "$log" 2>/dev/null | tail -1 | tr -d '[]' || true)
      tot_c=$(grep -aoE 'perplexity over [0-9]+ chunks' "$log" 2>/dev/null | tail -1 | grep -oE '^[0-9]+|[0-9]+' | tail -1 || true)
      rows=$(grep -ac '^| ' "$log" 2>/dev/null || echo 0)
      if [[ -n ${done_c:-} && -n ${tot_c:-} ]]; then msg="$msg  chunk $done_c/$tot_c"
      elif (( rows > 0 )); then msg="$msg  $rows bench row(s) done"
      else msg="$msg  (no progress markers yet)"; fi
    fi

    # A log that has not grown in STALL seconds is worth surfacing: it is either a
    # very long single pass or a hang, and those look identical from outside.
    size=$(stat -c %s "$log" 2>/dev/null || echo 0)
    age=$(( $(date +%s) - $(stat -c %Y "$log" 2>/dev/null || date +%s) ))
    if (( size == last_log_size && age > STALL )); then
      msg="$msg  [log silent ${age}s — long single pass, or stalled]"
    fi
    last_log_size=$size
    msg="$msg  ($(basename "$log"))"
  fi

  echo "$msg"
  sleep "$INTERVAL"
done
