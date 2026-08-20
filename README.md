# Running Claude Code against local models on a DGX Spark

Measurements, and a falsification pass over them, from running Claude Code against
locally-hosted models on an NVIDIA DGX Spark (GB10, 121 GB unified memory).

The headline: **96.4% of the redundant prefill in a real agentic session comes from
one interaction between how Claude Code sends system messages and how DeepSeek V4's
chat template renders them.** One template override removes it.

On a 10-task agentic eval built from real closed issues — scored by the project's
own gcc / cppcheck / clang-tidy / MISRA gate — that override took the local model
from **4/10 to 10/10 solved**, in 40% less wall-clock, with **17× less prefill per
turn**. See [15a](findings/verified/15a-a-trailing-system-message-rewrites-the-head.md),
[15b](findings/verified/15b-inline-rendering-removes-96-percent-of-redundant-prefill.md)
and [15c](findings/verified/15c-the-patched-template-solves-10-of-10.md).

## Start here

| | |
|---|---|
| **[findings/](findings/)** | What is true. One claim per file, and the directory is the status. |
| **[NOTES.md](NOTES.md)** | How it was tested — every experiment, every wrong assumption, the traps. |

The two are deliberately separate. `findings/` states conclusions with no archaeology;
NOTES holds the process, including the assumptions that turned out to be wrong (the
original document's *and* those made during verification).

Each finding is one file with a `status:` in its frontmatter, and it sits in the
directory that matches. There is no `corrected` status — a correction is a fact
about a claim's history, so a file that replaced an earlier figure carries a
`supersedes:` field, and a recommendation that turned out to be false lives in
`findings/refuted/`. Run `tools/findings-index.py` to regenerate the index and
validate the cross-links.

## Why there are two documents

The original findings were **observational** — sessions were run, logs were read
afterwards, mechanisms inferred from correlation. That is enough to form a
hypothesis and not enough to bet weeks on, and these conclusions were driving real
decisions.

So every finding was re-tested as though it were **wrong**, with a discriminating
outcome written down *before* each test ran. Several did not survive:

Four of them were false outright and live in
[findings/refuted/](findings/refuted/):

| claimed | measured |
|---|---|
| [`CLAUDE_SLOW_FIRST_BYTE_MS` fixes prefill timeouts](findings/refuted/05c-slow-first-byte-ms-fixes-prefill-timeouts.md) | **That variable does nothing.** `API_TIMEOUT_MS` is the knob, and it only shortens. Default budget is ~301 s, not 1800 s |
| [`--cache-type q8_0` is "the highest-leverage flag for long-context decode"](findings/refuted/06b-q8-0-kv-speeds-up-long-context-decode.md) | **Zero decode speedup.** Halving KV bytes changed nothing at any depth — it is a memory-capacity flag |
| [MXFP4's fewer bytes make it decode faster](findings/refuted/07b-mxfp4-outdecodes-q8-0.md) | **0.79×, not the predicted 1.21×.** Decode has no native FP4 path and pays dequant per byte |
| [Cache reset caused by a 128-token sliding window](findings/refuted/16b-cache-reset-is-caused-by-a-small-sliding-window.md) | The server is never told the window size at all — one hardcoded `return 0` |

Others were right in direction and wrong in magnitude. Those kept their claim and
carry a `supersedes:` field naming what they replaced — output costs
[~17× input, not ~38×](findings/verified/14-output-tokens-cost-17x-input-tokens.md),
and the disk KV cache is worth
[9.6× on a cold start, not ~1000×](findings/verified/01b-disk-kv-cache-is-worth-9-6x-on-a-cold-start.md).

## Layout

```
findings/            conclusions, one claim per file, filed by status
  verified/            survived a deliberate attempt to falsify it
  unverified/          measured once, with the completing test named
  refuted/             tested and found false, kept so nobody re-derives it
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
- **Five claims sit in [findings/unverified/](findings/unverified/)** — measured
  once, not yet re-tested. Each names the test that would close it. Two further
  rows inside [06c](findings/verified/06c-kv-cost-per-token-by-architecture.md)
  are calculated rather than measured, and are marked in place.
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
E5's answer is
[09c](findings/verified/09c-damage-tracks-mismatch-not-stretch-factor.md): there is no threshold in the
stretch factor, because the damage tracks mismatch with the trained mapping, not
the multiplier.

## Hardware

`gx10-52c8`, NVIDIA DGX Spark (GB10), compute capability 12.1, 121 GB unified
LPDDR5X at ~273 GB/s theoretical / ~221 GB/s measured, aarch64, CUDA 13.0.
