# Running Claude Code against local models on a DGX Spark

Measurements, and a falsification pass over them, from running Claude Code against
locally-hosted models on an NVIDIA DGX Spark (GB10, 121 GB unified memory).

The headline: **96.4% of the redundant prefill in a real agentic session comes from
one interaction between how Claude Code sends system messages and how DeepSeek V4's
chat template renders them.** One template override removes it.

On a 10-task agentic eval built from real closed issues — scored by the project's
own gcc / cppcheck / clang-tidy / MISRA gate — that override took the local model
from **4/10 to 10/10 solved**, in 40% less wall-clock, with **17× less prefill per
turn**. See [FINDINGS.md](FINDINGS.md) §15.

## Start here

| | |
|---|---|
| **[FINDINGS.md](FINDINGS.md)** | What is true. Every finding carries a confidence marker. |
| **[NOTES.md](NOTES.md)** | How it was tested — every experiment, every wrong assumption, the traps. |

The two are deliberately separate. FINDINGS states conclusions with no archaeology;
NOTES holds the process, including the assumptions that turned out to be wrong (the
original document's *and* those made during verification).

## Why there are two documents

The original findings were **observational** — sessions were run, logs were read
afterwards, mechanisms inferred from correlation. That is enough to form a
hypothesis and not enough to bet weeks on, and these conclusions were driving real
decisions.

So every finding was re-tested as though it were **wrong**, with a discriminating
outcome written down *before* each test ran. Several did not survive:

| finding | claimed | measured |
|---|---|---|
| #5 | `CLAUDE_SLOW_FIRST_BYTE_MS` fixes prefill timeouts | **That variable does nothing.** `API_TIMEOUT_MS` is the knob, and it only shortens. Default budget is ~301 s, not 1800 s |
| #6 | `--cache-type q8_0` is "the highest-leverage flag for long-context decode" | **Zero decode speedup.** Halving KV bytes changed nothing at any depth — it is a memory-capacity flag |
| #7 | MXFP4's fewer bytes make it decode faster | **0.79×, not the predicted 1.21×.** Decode has no native FP4 path and pays dequant per byte |
| #14 | Output costs ~38× input | Depth-mismatched. **~17×** at matched depth |
| #15 | Cache reset caused by a 128-token sliding window | The server is never told the window size — one hardcoded `return 0` (see §16) |

## Layout

```
FINDINGS.md          conclusions, with confidence markers
NOTES.md             methodology, test log, falsified assumptions
tools/               the verification harness
templates/           stock and patched DeepSeek V4 chat templates
results/             per-test writeups and the pre-verification original
data/                raw measurement output — benches, replays, session logs
server-scripts/      model server launchers used on the box
```

## The harness

Built because nothing existing measured the *rendered* prompt, which is the only
thing that matters for prefix caching.

| tool | what it does |
|---|---|
| `render.py` | Anthropic body → OpenAI → `/apply-template` → `/tokenize`. Faithful port of llama.cpp's own converter; validated to **delta 0** against `/v1/messages/count_tokens` on all 13 captures |
| `prefix.py` | Longest common **token** prefix, plus shift-recoverability by n-gram scan |
| `replay.py` | Replays captured bodies at `max_tokens:1` — identical input, one variable |
| `logparse.py` | Per-task prefill/decode/reuse from server logs; reproduces the published case study exactly |
| `quality.py` | Greedy output A/B across two sequentially-run server arms |
| `patch-template.py` | Builds the E7 template by auditable exact-string patch |
| `arm.sh` / `run-queue.sh` / `phase6.sh` | One-flag-different server arms, and unattended test queues |
| `stub-server.py` | Never-answering `/v1/messages`; measures the client's abort in one trial |

### Setup

```bash
ln -sf ../../tools/pre-commit-guard.sh .git/hooks/pre-commit
```

Do this before your first commit. The guard refuses anything shaped like a
captured request body, a Claude Code session marker, a device/session id, or a
credential — regardless of filename or `.gitignore`. It exists because this repo
published a set of transcripts once; see below.

### Captures are not published

The harness reads captured `/v1/messages` bodies, which are raw session
transcripts. Those are **deliberately not in this repo** — capture your own:

```bash
server-scripts/dump-proxy.py                 # :8004 -> :8003, writes ~/e1-dumps
ANTHROPIC_BASE_URL=http://<host>:8004 claude  # then work normally
```

**This went wrong once, and the tooling now prevents it.** `dump-proxy.py` used
to restart its sequence counter at 1, silently overwriting `req-00001.json`
onward *in place*. Eight requests of one session were replaced by an unrelated
session, and the substitution was invisible — the files still parsed and still
had plausible message counts — until their token counts were re-derived and
stopped matching. That set had already been published.

Three layers now stop it:

1. `dump-proxy.py` resumes numbering past whatever exists and creates files
   exclusively (`open(..., "xb")`), so a capture can never be clobbered.
2. `.gitignore` excludes the known paths and filename shapes.
3. `tools/pre-commit-guard.sh` blocks by *content shape*, catching transcripts
   that were copied, renamed, or pasted somewhere new.

### Reproducing the headline result

Requires DeepSeek-V4-Flash UD-IQ3_XXS and a llama.cpp build. All numbers here are on
llama.cpp commit `687e778`; running `build-llamacpp.sh` will move you off it.

```bash
# token level — no GPU work, ~2 hours
llama-server -m <v4> --jinja --port 8003 &                      # stock template
llama-server -m <v4> --jinja --port 8011 \
    --chat-template-file templates/dsv4-inline-assistant.jinja &
tools/prefix.py --compare http://127.0.0.1:8011

# wall clock — two cold-cache arms
tools/arm.sh stock   && tools/replay.py --tag stock
tools/arm.sh patched && tools/replay.py --tag patched
```

## Caveats worth reading before citing anything

- **The bench noise floor is ~4%, not the ± `llama-bench` prints.** The same row
  across four process launches spans 4.3% while the reported within-run sigma is
  0.1–0.7%. Treat any difference under ~5% as noise.
- **`llama-server` binds its chat template at startup.** `/apply-template` silently
  ignores a `chat_template` in the request body, so a per-request A/B compares two
  identical streams and reads as "no effect".
- **Seven findings are still marked `[unverified]`** — measured once, not yet
  re-tested. They are labelled as such in FINDINGS.md.
- **The E7 template fix is now proven on both throughput and task success**
  (10/10 vs 4/10 on the eval). Stock's 4/10 is a *lower bound* — 9 of its 10 tasks
  hit the 90-minute cap — so the supported claim is "under a fixed time budget,
  patched solves 2.5× as many", not that the template makes the model smarter.

## The eval

`tools/eval-build.py` assembles tasks from closed issues whose fix PR added a
runnable regression fixture, and verifies each one fails on the buggy base commit
*and* passes with the known-good patch. Candidates that pass on the base (the test
does not capture the bug) or fail even with the reference fix (unwinnable) are
discarded — both would corrupt a score, in opposite directions.

`tools/eval-run.py` scores a model by driving Claude Code against a local server,
editing the repo with tools. Results in `results/eval/`.

**Every experiment the original document opened is now closed** — E1 through E7.
E5's answer is in [FINDINGS.md](FINDINGS.md) §9: there is no threshold in the
stretch factor, because the damage tracks mismatch with the trained mapping, not
the multiplier.

## Hardware

`gx10-52c8`, NVIDIA DGX Spark (GB10), compute capability 12.1, 121 GB unified
LPDDR5X at ~273 GB/s theoretical / ~221 GB/s measured, aarch64, CUDA 13.0.
