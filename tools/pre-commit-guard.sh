#!/usr/bin/env bash
# pre-commit-guard.sh — refuse to commit raw session transcripts.
#
# This exists because it already went wrong once. Captured /v1/messages bodies
# are complete session transcripts: whatever you were working on, every path,
# every word you typed. A set of them was published here before anyone noticed
# that a proxy restart had silently replaced eight of them with an unrelated
# session -- one that happened to be job-application material.
#
# .gitignore stops the known paths. This stops the ones nobody thought of: a
# transcript copied somewhere new, renamed, or pasted into a doc.
#
# Install:  ln -sf ../../tools/pre-commit-guard.sh .git/hooks/pre-commit
# Bypass:   git commit --no-verify        (think hard first)

set -uo pipefail

fail=0
dash="-"
note() { echo "  $*" >&2; }

staged=$(git diff --cached --name-only --diff-filter=ACM)
[[ -z $staged ]] && exit 0

while IFS= read -r f; do
  [[ -f $f ]] || continue
  git check-attr -a -- "$f" 2>/dev/null | grep -q 'binary: set' && continue

  # 1. Anthropic/OpenAI request bodies: a messages array of role/content pairs.
  #    This is the shape that matters, whatever the file is called.
  if head -c 200000 "$f" 2>/dev/null | grep -qE '"messages"[[:space:]]*:[[:space:]]*\[' &&
     head -c 200000 "$f" 2>/dev/null | grep -qE '"role"[[:space:]]*:[[:space:]]*"(user|assistant|system)"'; then
    note "TRANSCRIPT: $f looks like a captured request body (messages[] with role/content)"
    fail=1
  fi

  # 2. Client-injected markers that only appear inside real sessions.
  #    Patterns are assembled from fragments so this script never contains the
  #    literal strings it searches for -- otherwise the guard flags itself.
  marker="<system${dash}reminder>|Session""Start hook additional|UserPrompt""Submit hook"
  if grep -qE "$marker" "$f" 2>/dev/null; then
    note "TRANSCRIPT: $f contains Claude Code session markers"
    fail=1
  fi

  # 3. Machine and session identifiers.
  if grep -qE '"(device_id|account_uuid|session_id)"[[:space:]]*:[[:space:]]*"[0-9a-f-]{8}' "$f" 2>/dev/null; then
    note "IDENTIFIER: $f contains a device/account/session id"
    fail=1
  fi

  # 4. Credentials.
  if grep -qE 'gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|BEGIN [A-Z ]*PRIVATE KEY' "$f" 2>/dev/null; then
    note "CREDENTIAL: $f contains what looks like a real token or key"
    fail=1
  fi
done <<< "$staged"

if (( fail )); then
  cat >&2 <<'EOT'

pre-commit guard: refusing to commit.

Captured request bodies are raw session transcripts and must not be published.
If a file above is a false positive, either exclude it or use --no-verify -- but
read the file first, in full, and be certain of which session produced it.

EOT
  exit 1
fi
exit 0
