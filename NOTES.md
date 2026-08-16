# Verification notes — how `FINDINGS.md` was tested

Companion to `FINDINGS.md`, which states only conclusions. This document
holds the process: what was tested, what each test predicted *before* it ran,
what came back, and every assumption that turned out to be wrong — the original
document's and my own.

Machine: `gx10-52c8` (GB10, cc 12.1, 121 GB). llama.cpp pinned at `687e778`.
Verification run 2026-08-12. Raw logs in `data/`, harness in `tools/`.

---

## Why a falsification pass

The original findings were **observational**. Sessions were run, logs were read
afterwards, and mechanisms were inferred from correlation:

- #15 rested on 9 opportunistically captured requests
- #4 rested on a single divergence event
- #1's headline changed two variables at once
- #13's causal attribution was argued, not measured

That is enough to form a hypothesis and not enough to bet weeks on — and these
conclusions were driving real decisions (E6 dropped, the custom-quant project
cancelled, E7 queued as highest value).

So each finding was treated as **wrong until a measurement said otherwise**, with
a discriminating outcome written down *before* the test ran.

---

## Assumptions that turned out to be wrong

### In the original document

| # | Claimed | Actually |
|---|---|---|
| 3 | Checkpoint interval ~20,480 tokens | **10,240** (`interval 10000` aligned up to `align 2048`) |
| 3 | Eviction is hit-weighted, killing unused rungs | Hit-weighting is `(hits+1)` — weak. The dominant term is `kv_cache_incoming_supersedes_continued`, a **×0.05** penalty on superseded rungs |
| 3 | ~21 snapshots totalling ~46 GiB | Does not follow from the interval, from 13.5 KiB/token, or from cumulative prefixes. Unconfirmed |
| 5 | Budget is 1800 s | **~301 s by default** |
| 5 | Set `CLAUDE_SLOW_FIRST_BYTE_MS` to fix it | **That variable does nothing.** `API_TIMEOUT_MS` is the knob, and it only shortens |
| 7 | "MXFP4 is the only quant with hardware acceleration on GB10" | True **only for prefill**. Decode has no Blackwell-gated FP4 path at all |
| 8 | llama-bench matched production to 4 significant figures | The depths differed (65,536 vs 62,903). Agreement that exact is luck, not evidence |
| 14 | Output costs ~16–38× input | The 38× divides *shallow* prefill by *deep* decode. At matched depth it is **17×** |
| 15 | Reset caused by a 128-token sliding window leaving no state at position 9,200 | The server is never told the window size. `llama_model_n_swa()` returns **0** for DEEPSEEK4 — see #16 |
| 15 | Insertion lands "~9,200 tokens in, about 6%" | Measured **9,595–9,838 tokens, 6.5–6.7%** |
| 13 | Custom-quant marginal return "~30%" | **+6.8% to +13.7%** — only 40.1% of params fit at MXFP4 |

### Mine, during this pass

| Assumed | Actually |
|---|---|
| Patching only `use_native_fp4` gives a clean FP4 ablation | **It produces `nan`.** `mmq.cuh:244` still picks Blackwell FP4 tile configs, so the layout mismatched the q8_1 data path. Ran 1.73× "faster" while computing garbage |
| `/apply-template` honours a `chat_template` in the request body | **Silently ignored.** The template is bound at server startup. My first template A/B returned two byte-identical streams and read as "the patch changed nothing" |
| A CPU-only tokenizer server could coexist with the 112 GB production server | mmap-loading a 100 GB model against mlocked memory thrashes; it eventually loaded but was not viable alongside real work |
| The server would reuse the ~9,700-token common prefix on a head change | Reuse is **0**. I predicted partial reuse from reading the code path and was wrong — see #16 for why |
| Whole-string common *suffix* measures shift-recoverability | It does not. These requests insert at the head *and* append at the tail, so the suffix is short for an unrelated reason. Needed an n-gram scan from the divergence point |
| `pkill -f <pattern>` is safe | It matches **its own shell** when the pattern appears in the command line. Hit this **five times**, twice silently skipping the thing it guarded. Use `pgrep -x` on the exact process name, a recorded PID, or memory usage instead |
| Patching one side of a host/device pair is a clean ablation | It is not. v1 patched `use_native_fp4` only; `mmq.cuh:267` still selected Blackwell tiles on the device. Ran 1.73x "faster" and produced `nan`. **A performance ablation without a correctness gate is not an experiment** |
| An equality gate validates an ablation | Only when the paths *should* be identical. For MXFP4 they legitimately differ (4-bit vs 8-bit activations), so equality flagged a valid ablation as broken. Compare against a **control** that must not change |
| A published capture set stays what you analysed | `dump-proxy.py` reset its counter on restart and overwrote eight captures in place with an unrelated session. Invisible until token counts stopped matching — after publication |
| The checkpoint interval is the configured constant | It is the *realised spacing*. Reading `interval 10000` aligned to 2048 gave 10,240; measurement gave 20,189. Retracted |

---

## Instruments

Built first, because none of the existing tooling measured the rendered prompt.

| Tool | What it does | How it was validated |
|---|---|---|
| `render.py` | Anthropic body → OAI → `/apply-template` → `/tokenize`. Line-by-line port of `server_chat_convert_anthropic_to_oai()` | Token count equals the server's own `/v1/messages/count_tokens` on all 13 captures, **delta 0** |
| `prefix.py` | Longest common **token** prefix + shift-recoverability by n-gram scan | Replaces `analyze-divergence.py` |
| `logparse.py` | Per-task prefill/decode/reuse from server logs | **Reproduces the published case study exactly** |
| `replay.py` | Replays captured bodies at `max_tokens:1` — identical input, one variable | Predicted prefill matched measured to within 5 tokens over 13 requests |
| `patch-template.py` | Builds the E7 template by exact-string patch, two cutoff variants | 4 edits, each asserted to apply exactly once |
| `quality.py` | Greedy A/B of generations across two sequentially-run arms | — |
| `arm.sh` | One-flag-different server arms at matched 256k context | — |
| `stub-server.py` | Never-answering `/v1/messages`; measures the client's abort by watching for the retry | — |
| `fp4-ablation.sh` | Patches `use_native_fp4` behind `GGML_CUDA_NO_FP4`, pinned to `687e778` | Refuses to run if the checkout moved |

### `analyze-divergence.py` is unsound

The pre-existing tool reports `REWRITE` on **12 of 12** consecutive request pairs.
In 8 of them the only JSON difference is Claude Code's prompt-cache breakpoint
moving forward:

```
A: ..., "cache_control": {"type": "ephemeral"}}]}
B: ...}]}
```

It hashes `json.dumps(message)`, so metadata that never reaches the model reads as
a content rewrite. **Nothing derived from its output should be cited.** Its own
docstring warns that an earlier version "classified purely by message index and
called a harmless trailing-system-message change a fatal REWRITE" — the same
class of bug, one level down.

---

## Test log

Each entry: the null hypothesis, the discriminating outcome registered in
advance, and the result.

### V15.1 — does in-place rendering preserve the prefix? ✅

> **Registered:** E7's premise is proved if stock LCP ≈ 9.2k while patched
> LCP ≈ 100%. E7 is dead if patched LCP is also small.

Two servers (stock template on :8003, patched on :8011 via
`--chat-template-file`), 13 captured requests, token-level common prefixes.

| | total re-read | expensive (>20k) |
|---|---:|---:|
| stock | 423,752 tok | 3 |
| patched | **14,123 tok** | **0** |

**96.7% removed, before any GPU work.** Cost: ~2 hours.

Residual on #2→#3 (2,391 tokens) is not a template bug — detokenised, the lost
tail is an ephemeral *user* message ("The user stepped away and is coming
back…") that the client did not retain. Genuine content change at 98.3% depth.

### V15.2 — does it hold in wall-clock? ✅

Two arms, one flag apart, each restarted for a cold cache, same 13 bodies at
`max_tokens: 1`.

| | prefilled | wall |
|---|---:|---:|
| stock | 591,519 tok | 38.8 min |
| patched | 154,705 tok | 10.5 min |

**96.4% of redundant prefill removed** against V15.1's predicted 96.7%.

Per-request prediction vs measurement:

| req | V15.1 predicted | V15.2 measured |
|---|---:|---:|
| #8 | 1,149 tok | **1,149 tok** |
| #9 | 396 tok | **396 tok** |

Reuse is read straight from the Anthropic response (`input_tokens` +
`cache_read_input_tokens`), which also cross-checks `render.py` for free.

### V15.4 — can `--swa-full` recover the discarded prefix? ❌

> **Registered:** survives if `--swa-full` recovers the ~9,700-token reuse —
> mechanism confirmed *and* a config-only mitigation. Refuted if reuse stays 0.

Answered at load time, before any request:

```
W srv  load_model: swa_full is not supported by this model, it will be disabled
```

**The mitigation does not exist.** No replay was run — the arm is functionally
identical to stock and would have reproduced known numbers for ~40 minutes.

Root cause traced to one hardcoded `return 0` with three consequences → became
finding #16.

### V15.5 — does the template change what the model does? ⚠️

Five prompts, temperature 0, reasoning blocks compared as well as text (V4 Flash
spends much of a short budget thinking; a text-only comparison would call two runs
identical when neither had begun to speak).

**identical output: 1/5 · same tool calls: 3/5**

The two differences:

- **#7** — both arms emit two `Bash` calls; the second effectively identical. The
  first differs (`npm run unit:coverage` vs `git log --oneline --since=…`). Two
  reasonable next steps in an open-ended task.
- **#9** — stock: `TaskUpdate{status:completed}`, reasoning *"I got a task
  notification earlier that it completed… let me just proceed"*. Patched: `Read`
  on the actual output file, reasoning *"The validate:c completed. Let me check
  its output."* The patched arm verifies rather than assumes.

#9 is the case the patch should most affect: it ends in a `[SYSTEM NOTIFICATION]`
block that stock hoists ~9,800 tokens away from the turn it refers to.

**Verdict: n=5 supports no claim of quality preservation.** Nothing observed is
worse; that is not the same as safe.

### V5 — the client's timeout ⚠️

> **Registered:** the stub measures the budget in one trial by watching for the
> retry, rather than bisecting at one timeout per probe.

| probe | config | budget |
|---|---|---:|
| A | *(default)* | **300.9 s** |
| B | `CLAUDE_SLOW_FIRST_BYTE_MS=60000` | 300.9 s — no effect |
| D | `CLAUDE_SLOW_FIRST_BYTE_MS=600000` | 300.8 s — no effect |
| C | `API_TIMEOUT_MS=60000` | **60.5 s** — works |
| E | `API_TIMEOUT_MS=900000` | 301.0 s — cannot raise |

Probe A ran to completion: **11 POSTs = 1 initial + exactly 10 retries**, then
`Request timed out`. 58 minutes for one request. Backoff additive (300.9 →
335.1 s), not exponential. Body hash identical throughout.

**Known limitation.** The stub never sends a byte; `llama-server` does. The case
study contains prefills of **812.7 s that completed**, so a hard 301 s cap is not
the production failure mode — likely `message_start` (`server-task.cpp:1360`) is
emitted on task acceptance, making the *idle* timeout binding. Completing test:
time the first SSE byte on a real streaming request at a cold cache.

### V7.1 — is MXFP4 fast because of tensor cores? ❌ **attempt invalid**

> **Registered:** survives if MXFP4's advantage collapses toward 1.0× with the
> native path off. Refuted if it still wins by ~1.2–1.4×, meaning the gain is
> bytes and unpack cost, not tensor cores.

Neither. **The ablation itself was broken and the test did not run.**

The patch flipped `use_native_fp4` at `mmq.cu:131` behind `GGML_CUDA_NO_FP4`,
deliberately *not* touching `blackwell_mma_available()` because `mmq.cuh` has a
host-side config selector and a `__device__` selector using compile-time macros —
flipping the shared helper would desynchronise them.

That reasoning was right and I walked into the mirror-image of it anyway.
`mmq.cuh:244` still calls `blackwell_mma_available(cc)` and returns
`ggml_cuda_mmq_get_config_blackwell(...)`, so **the tile config stayed FP4 while
the data went through q8_1**.

| | pp4096, ub 512 |
|---|---:|
| baseline, native on | 1872.78 t/s |
| patched build, env unset (control) | 1859.99 t/s — patch inert ✅ |
| patched build, `GGML_CUDA_NO_FP4=1` | **3243.35 t/s** — 1.73× "faster" |

The control was clean, which made the 1.73× look real. Perplexity killed it:

```
NATIVE : Final estimate: PPL = 3.9655 +/- 0.13663
DEQUANT: [1]nan,[2]nan,[3]nan,[4]nan,
         E Unexpected negative standard deviation of log(prob)
```

**Fast because it was computing nothing.** `llama-bench` never checks output, so
throughput alone would have shipped a fabricated finding.

Incidental confirmation the env var never reached the config path: `system_info`
still printed `BLACKWELL_NATIVE_FP4 = 1`, which comes from `ggml-cuda.cu:5405`
calling `blackwell_mma_available()` directly.

**What a valid attempt needs:** a compile-time build variant so host and device
configs move together, plus a perplexity gate before any throughput number is
believed. Source reverted to pristine at `687e778` and rebuilt; the baseline
reproduces.

**Lesson worth generalising:** a performance ablation without a correctness gate
is not an experiment. Every future kernel-path test gets perplexity first,
throughput second.

### V7.1 — is MXFP4 fast because of tensor cores? ✅ **answered on the second attempt**

> **Registered:** ratio collapses toward 1.0 -> the native path is the cause.
> Ratio holds at 1.2-1.4x -> the advantage is bytes, and #13 is misattributed.

**v1 was invalid** (see the wrong-assumptions table). v2 suppresses Blackwell MMA
via a single compile-time flag that both selectors derive from, so host and device
move together:

```
common.cuh:286  #if __CUDA_ARCH__ >= BLACKWELL   -> BLACKWELL_MMA_AVAILABLE  (device)
common.cuh:360  blackwell_mma_available(cc)                                  (host)
```

The patch is inert without `-DGGML_NO_BLACKWELL_MMA`, so the pristine build stays
comparable. Verified the flag took effect before measuring anything:
`system_info` prints `ARCHS = 1210 ... BLACKWELL_NATIVE_FP4 = 1` on pristine and
`ARCHS = 1210 ...` on ablated — same arch, feature gone, so no JIT confound.

**Q4_K_M is the control.** It never enters the FP4 branch, so the flag must be a
no-op for it:

| | pristine | ablated | delta |
|---|---:|---:|---:|
| pp4096 ub512 | 1275.60 | 1296.95 | +1.7% |
| pp65536 ub512 | 997.50 | 1007.23 | +1.0% |
| pp4096 ub2048 | 1807.27 | 1819.86 | +0.7% |

All within the 4% noise floor, while MXFP4 slows 15-24%. That is what makes the
result trustworthy where v1's was not.

**Result:** native FP4 path **1.16-1.34x**; bytes and unpack **1.04-1.11x**;
accuracy cost **PPL 7.5423 -> 8.0227 (+6.4%)** because the path quantises
activations to 4-bit (`block_fp4_mmq`) rather than 8-bit (`block_q8_1_mmq`).

**The gate as written was wrong.** It demanded the ablated build match the
pristine build exactly, and flagged MXFP4 as invalid. But the two paths are not
*supposed* to be numerically identical for MXFP4 — different activation precision
is the whole point. The Q4_K_M control is what established soundness. A pass/fail
equality gate was the wrong shape; it should compare against the control.

**Honest limit:** the branch bundles Blackwell FP4 MMA and 4-bit activations, so
this cannot isolate the tensor cores specifically.

### V12.2/V12.3 — is 2048 the ubatch optimum, or just the largest tried? ✅

| ubatch | pp4096 | pp65536 |
|---:|---:|---:|
| 512 | 1878.57 | 1339.67 |
| 1024 | 2024.66 | 1447.92 |
| **2048** | **2254.42** | **1620.40** |
| 4096 | 2219.48 | 1579.74 |

**2048 is a genuine peak.** 4096 is 2.5% slower at pp65536 with error bars of
+/-1.2, so that is real rather than noise.

Note the pp4096 rows carry huge error bars (+/-280 at ub1024, +/-111 at ub2048):
a 4096-token prompt at large ubatch is only a couple of batches, so per-run
variance dominates. The pp65536 rows are the trustworthy ones. This applies to
any shallow-depth bench row, including some in the original document.

### V6.2 — is decode at depth bound by the KV read? ❌ refuted

| depth | f16 KV | q8_0 KV |
|---:|---:|---:|
| 0 | 63.34 | 61.70 |
| 16,384 | 41.86 | 41.43 |
| 65,536 | 20.21 | 20.65 |
| 131,072 | 12.13 | 12.12 |

Halving KV bytes changed decode by **0-2% at every depth**. With flash attention
the KV is read in tiles and dequantised on the fly, so q8_0 halves traffic while
leaving the arithmetic identical — unchanged timing means arithmetic is binding.

Shallow decode *is* bandwidth-bound as claimed: 63.34 t/s x 3.5 GB/token =
**221 GB/s**, matching the document's ~227.

### V7.3 — the decode corollary ❌ refuted

gpt-oss MXFP4 **50.21 t/s** vs Qwen Q8_0 **63.34 t/s** at matched shallow depth.
Predicted 1.21x in gpt-oss's favour; measured **0.79x**. Effective bandwidth
143 GB/s vs 221. Decode has no native FP4 path, so MXFP4 pays dequant per byte.

### V9.2 — do rope flags apply inside the training window? ✅ / corruption ❌

| arm | PPL |
|---|---:|
| no rope flags | 4.7195 +/- 0.08943 |
| `--rope-scale 2` | 4.5520 +/- 0.08650 |

Perplexity is **bit-exact deterministic** — rerunning the reference reproduced
`4.7195 +/- 0.08943` to four decimals — so the difference is caused entirely by
the flag. The flags are applied. But output *improves* 3.5%; at 2048 context,
positions 0-2047 map to 0-1023 and stay inside trained range, so nothing is
extrapolated. The corruption claim remains untested where it would bite.

Capping is `llama-server`-specific; `llama-perplexity` at `-c 262144` only warns.

### V1.1 — is the disk KV cache worth 1000x? ⚠️ 9.6x

| arm | config | cold prefill |
|---|---|---:|
| A | no `--kv-disk-dir` | 370.1 s |
| C | disk enabled, cold | 376.6 s |
| D | disk enabled, **after restart** | **38.8 s** |

Only a restart empties the live cache, so only arm D isolates disk. It loaded a
104,944-token checkpoint in **163 ms** and prefilled the remaining 9,482.
Mechanism real; headline inflated ~100x by the original confound.

### V2 — two ids, one model ✅

```
ids:            ['deepseek-v4-flash', 'deepseek-v4-pro']
distinct names: {'DeepSeek V4 Flash'}
```

### V3.1 — the checkpoint ladder ✅ (and a retraction)

6 files, 5.4 GiB for a 120,699-token conversation, spaced **20,189 tokens**, at
**13.64 KiB/token**. Scaled to 320k: ~16 files, ~38 GiB vs the stated ~21 / ~46.

**Retraction:** an earlier pass in this same verification "corrected" the interval
to 10,240 from reading the constant. That is the *configured step*;
`ds4_kvstore_continued_store_target()` fires only when `live_tokens % step == 0`
and prefill lands on every second multiple. The original document was right.

### V4.2 — the two-engine comparison ⚠️ confounded

The same conversation renders to **114,426 tokens on ds4-server** and **140,656 on
llama.cpp** — a 19% gap from different chat templates. "Identical input, two
engines" is not achievable at the token level.

### V13.3 — how much of V4 could take the MXFP4 path? ✅

Read from the actual GGUF tensor list across all four shards:

| type | tensors | params | share |
|---|---:|---:|---:|
| IQ2_S | 84 | 180,388,626,432 | 63.4% |
| IQ3_XXS | 41 | 88,046,829,568 | 31.0% |
| Q8_0 | 321 | 4,928,307,200 | 1.7% |
| MXFP4 | 2 | 4,294,967,296 | 1.5% |
| IQ3_S | 2 | 4,294,967,296 | 1.5% |
| Q6_K | 170 | 2,292,187,136 | 0.8% |
| **total** | **1328** | **284,334,567,511** | |

94.6 GiB computed (reported 95.9). Pure MXFP4 = 140.7 GiB (doc said 144.3). At a
106 GiB weight budget with the rest pinned at the IQ2_S floor, **40.1% of
parameters** are promotable → **+6.8% to +13.7%** overall.

Interlock: this number is only meaningful if V7.1 confirms tensor cores are the
cause. If the advantage is bytes-driven, promoting IQ2_S (2.5 bpw) to MXFP4
(4.25 bpw) makes tensors *larger* and the sign flips.

### V8.2 / V12 / V13.1 — bench matrix re-run ✅ (partial)

Same commit, same harness, 3 repetitions.

MXFP4, all six rows reproduce within **±4%**:

| test | ub | published | re-measured |
|---|---:|---:|---:|
| pp4096 | 512 | 1800.58 | 1872.78 |
| pp16384 | 512 | 1732.18 | 1718.07 |
| pp65536 | 512 | 1310.39 | 1357.88 |
| pp4096 | 2048 | 2331.97 | 2355.89 |
| pp16384 | 2048 | 2186.64 | 2234.24 |
| pp65536 | 2048 | 1555.29 | 1611.47 |

#12's ubatch gain reproduces: **+25.8% / +30.0% / +18.7%** against the published
+29.5% / +26.2% / +18.7%.

Q4_K_M rows in progress at time of writing.

### Confirmed from source, no measurement needed

| Claim | Where |
|---|---|
| `--kv-cache-cold-max-tokens` default is 30000 | `ds4_kvstore.c:34`, `ds4_help.c:328` |
| GB10 qualifies for the native FP4 gate (cc 12.1) | `mmq.cu:131`, `common.cuh:360`, `nvidia-smi` |
| `get_can_shift()` returns false for DSV4; `n_cache_reuse` silently zeroed | `llama-kv-cache-dsv4.cpp:1394`, `server-context.cpp:1278-1291` |
| Rope params resolved independently of context capping | `server-context.cpp:1311-1313`, `llama-context.cpp:130-132` |
| Claude Code really does put `role:"system"` inside `messages` | all 13 captures: 4→7 per request |
| The V4 template hoists every system message to the head | live template lines 33–67 |
| Decode has no Blackwell-gated FP4 path | `mmvq.cu:19` vs `mmq.cu:131` |

### Reproduced exactly

The case study block — 858,025 tok / 73.4 min prefill, 8,280 / 11.1 min decode,
84.5 min total, 6 full re-reads, largest 154,431, redundant 677,213 = **68.6%** —
re-derived from `dsv4-session-frozen-20260809.log` by summing real per-task
milliseconds. Every figure matches.

#11's bimodality confirmed on a *second* independent session: 9 tasks at 0–9%
reuse, 19 at 90–99%, 3 between.

---

## Traps worth remembering

- **`/apply-template` ignores a per-request `chat_template`.** Silently. A
  template A/B that sets it returns two identical streams. `render.py` now raises
  rather than allow it.
- **`pkill -f <pattern>` matches its own shell.** Cost three self-killed commands,
  one of which silently skipped a `systemctl stop` and left the wrong server
  running. Use `pgrep -f 'stub[-]server'` bracket-escaping, or kill by PID.
- **A backgrounded child dies with a timed-out foreground command.** `nohup`
  ignores SIGHUP, not SIGTERM. Use `setsid`.
- **Placeholder substitution that eats syntax.** `role in [CUTOFF_ROLES]`
  replaced wholesale yields `role in 'a', 'b'` — a tuple expression, always truthy
  in jinja. Caught by diffing the two generated templates, not by testing.
- **`build-llamacpp.sh` runs `git pull --ff-only`.** Running it moves the checkout
  off the pinned commit and invalidates comparability. Rebuild in place instead.
- **`dsv4-proxy` has `Requires=dsv4-server`** — stopping the server stops the
  proxy; starting the server does not restore it.
- **`grep` matching its own banner text.** A wait loop keyed on `"CLIENT GAVE UP"`
  fired immediately against the stub's own startup message.

---

## Method notes

**Replay, not observation.** Every cache experiment in the original was "run a
session and hope a divergence happens", which is why n was small and confounds
were uncontrolled. Replaying captured bodies at `max_tokens: 1` makes the input
identical across arms so template/flag/engine is the only variable, and makes
prefill the whole cost rather than prefill plus 8,000 generated tokens.

**Token level, not JSON level.** The original document's own conclusion —
*"any cache analysis done on the client's request body will mispredict; the
rendered prompt is the only thing that matters"* — was correct and no tool
implemented it. Doing so turned "REWRITE vs SHIFT" from a judgement into
arithmetic.

**Predict, then measure.** V15.1 predicted per-request prefill from
`/apply-template` alone; V15.2 confirmed #8 = 1,149 and #9 = 396 exactly. That
agreement is what licenses using the cheap token-level instrument to screen ideas
before spending GPU hours.

**Cold caches between arms.** Each arm restarts, so every arm pays the same cold
prefill and later requests are comparable.

**The bench noise floor is ~4%, not the ± llama-bench prints.** The same
`pp4096 ub512` MXFP4 row, four independent launches:

| | t/s |
|---|---:|
| published (original session) | 1800.58 |
| today, pre-patch baseline | 1872.78 ± 12.43 |
| patched build, env unset | 1859.99 ± 10.07 |
| reverted build | 1795.72 ± 1.58 |

Spread **4.3%**; within-run sigma 0.1–0.7%. The GPU idles at 38 °C / 227 MHz, so
this is launch-to-launch state rather than thermal drift.

Consequences: any effect under ~5% is unresolvable by this harness; arms should
be interleaved A/B/A/B rather than run in sequence; and the reported ± should
never be quoted as the uncertainty. It also settles #8's four-significant-figure
production agreement — 0.02% agreement against a 4% noise floor is not evidence
of anything.

**Matched context across arms.** All arms run 256k, not the production 1M: the
captured prompts top out at 152,643 tokens, smaller loads faster, and `--swa-full`
would not have fit at 1M.

---

## Open queue

| Test | Question | Why it matters |
|---|---|---|
| **the eval** | 10–20 real issues, scored on compiles / fixes | Blocks E4, E5 **and** shipping E7's 96.4% win. Highest value in the project |
| **V7.1** | Is MXFP4's advantage tensor cores or bytes? | Decides whether #13's cancellation was right or backwards. **First attempt invalid** — needs a compile-time build variant, not a runtime flag |
| V1.1 | Isolate the disk cache from the live cache | #1's 1000× is currently unattributable |
| V3.1 | List the checkpoint directory | Settles #3's 46 GiB |
| V4.2 | Replay the same bodies against both engines | Settles whether #4 and #15 are the same phenomenon |
| V6.2 | Decode depth sweep, f16 vs q8_0 KV | Tests #6's causal claim |
| V9.2 | Perplexity / KL against an unflagged reference | Puts a number on #9's silent corruption |
| V10.1 | Both engines at matched quant/KV/context | #10 is uncontrolled |
| V15.3 | Re-capture without the 35 KB SessionStart hook | #15's generality |
| VC.1 | Classify each full re-read by measured cause | #68.6% is a lower bound |

**Standing recommendation:** keep `dsv4-proxy` in front of the server
permanently. The frozen case-study session is un-reanalysable purely because
request bodies were never captured, and that is the single biggest gap in the
existing evidence.
