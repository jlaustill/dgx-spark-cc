# Running Claude Code against local models on a DGX Spark

What is true, as measured on one machine over 2026-08-08/12.

Every finding carries a confidence marker:

| | meaning |
|---|---|
| **[verified]** | survived a deliberate attempt to falsify it — see `verify/` |
| **[corrected]** | the original claim was wrong or overstated; what follows is the corrected version |
| **[unverified]** | measured once, not yet re-tested against a falsification attempt |
| **[open]** | not answered |

The process, the falsified assumptions and the methodology live in
`NOTES.md`. This document is only the conclusions.

**The one sentence the rest of this follows from:** a DGX Spark buys capacity at
the price of bandwidth. Its 121 GB of unified LPDDR5X holds a 284B-parameter
model with a million tokens of context — which no consumer GPU can touch — and
moves bytes at roughly a quarter the speed of a dedicated card.

Unified memory removes one of the two hauls a normal GPU pays: there is no PCIe
copy from system RAM into VRAM, no offload decisions, no "does it fit on the
card". It cannot remove the second haul, DRAM into the compute circuits, because
that is what memory bandwidth *is*.

| | Bandwidth | Capacity |
|---|---:|---:|
| **GB10 (this box)** | ~273 GB/s | **121 GB** |
| RTX 5090 | ~1,800 GB/s | 32 GB |
| H100 | ~3,350 GB/s | 80 GB |

That trade explains the asymmetry every finding below circles around. **Prefill
batches**, so one weight-haul serves thousands of tokens and the memory pipe sits
~94% idle — prefill is compute-bound. **Decode cannot batch**, because you cannot
group a token you have not generated yet, so every single token pays a full haul
and runs straight into the wall.

---

## Where the time goes, and what fixes it

The case study measured **84.5 minutes of model time on one real agentic task**
[verified — reproduces exactly from the raw log]:

| Component | Measured | Share | Status |
|---|---:|---:|---|
| Necessary prefill | 15.5 min | 18.3 % | faster by `-ub 2048` [verified] |
| **Redundant prefill** | **57.9 min** | **68.6 %** | **cause found and fixed — see #15** |
| Decode | 11.1 min | 13.1 % | nothing here |

**The single largest cost in this document has one cause and one fix.** Claude
Code appends ephemeral `system`-role messages to the tail of the `messages`
array; DeepSeek V4's chat template hoists every system message to the head of the
rendered prompt. A tail append therefore becomes a near-head insertion ~9,700
tokens in, invalidating the 93% that follows.

Rendering mid-conversation system messages **in place** removes **96.4% of
redundant prefill** [verified, measured end to end]:

| | prefilled | wall |
|---|---:|---:|
| stock template | 591,519 tok | **38.8 min** |
| patched template | 154,705 tok | **10.5 min** |

Same 13 captured requests, two server arms differing in one flag, each from a
cold cache. Excluding the cold prefill both arms pay, redundant work drops from
452,924 tokens (30.1 min) to 16,106 (1.8 min).

**And it is not merely faster.** On a 10-task agentic eval scored by the
project's own gcc/cppcheck/clang-tidy/MISRA pipeline, the patched template solved
**10/10** against stock's **4/10**, in 40% less wall-clock. See #15.

## Open work

| # | Question | Status |
|---|---|---|
| **E4** | Can V4 Flash *write* a fix, not just analyse one? | ✅ **YES — 10/10 on the eval, patched template** |
| **E5** | Where is the rope-stretch tolerance threshold? | ✅ **ANSWERED — there is none in the stretch factor. See #9.** |
| **E7** | Does in-place system-message rendering fix the invalidation? | ✅ **ANSWERED — 96.4% of redundant prefill removed, and 10/10 vs 4/10 on the eval. Ship it.** |
| ~~E1~~ | What rewrites history mid-conversation? | ✅ answered — see #15 |
| ~~E2~~ | Does larger `--ubatch-size` help prefill? | ✅ answered — see #12 |
| ~~E3~~ | Does the native FP4 path beat a dequant format? | ✅ answered — see #13 |
| ~~E6~~ | DSV4 compressed-cache shifting | ❌ dropped — see #16 for the real reason |

**The eval now exists** — 10 real closed issues with known-good patches, scored
fail-then-pass on the project's own gate (`tools/eval-build.py`,
`tools/eval-run.py`). It answered E4 and E7's quality question. E5 remains open
and is now cheap to run against the same harness.

---

## Terminology

| Term | What the model is doing | llama.cpp log label | Bound by |
|---|---|---|---|
| **Prefill** | *Reading* input tokens, building KV | `prompt eval time` | compute — parallel across tokens |
| **Decode** | *Writing* output tokens, one at a time | `eval time` | memory bandwidth — serial |

Naming trap: bare **`eval time` is decode**; `prompt eval time` is prefill. They
sit adjacent in the log and are trivially easy to swap. `llama-bench` calls them
`tg` and `pp` respectively.

| Term | Meaning |
|---|---|
| **Necessary prefill** | The irreducible minimum — one pass over the context, plus the genuinely new tokens each turn adds |
| **Redundant prefill** | Re-reading tokens already processed, because cache invalidation threw the work away |

Redundant prefill is invisible in any single request — every prefill looks
legitimate on its own — and only appears when you sum a whole session.

---

## The machine

| | |
|---|---|
| Host | `gx10-52c8`, NVIDIA DGX Spark (GB10) |
| Compute capability | **12.1** (Blackwell) [verified] |
| Memory | 121 GB unified LPDDR5X, ~273 GB/s theoretical |
| Measured effective bandwidth | ~227 GB/s [unverified — derived from one shallow decode point] |
| Arch / toolchain | aarch64, CUDA 13.0, gcc 13.3 |
| Storage | NVMe, ~3.7 GB/s observed writes |
| llama.cpp | pinned at `687e778` — all numbers here are on this commit |

---

## 1. A default that silently disables the disk KV cache

**[verified — the default]** · **[corrected — the 1000× is 9.6×]**

`ds4-server` (antirez's DwarfStar engine) can persist KV checkpoints to disk, but
two things must both be true and only one is obvious:

```
--kv-disk-dir DIR                 # off by default
--kv-cache-cold-max-tokens N      # DEFAULT 30000
```

The default of 30000 is confirmed in source (`ds4_kvstore.c:34`,
`ds4_help.c:328`). Real coding-agent prompts here run 75k–400k tokens, so with
the default nothing is ever checkpointed even after enabling the directory.

**Symptom:** 82 requests in 24h, 82 misses, zero hits. Every turn re-prefilled
the entire conversation.

```
live kv cache miss live=321864 prompt=325568 common=1 reason=token-mismatch
```

**Fix:** `--kv-disk-dir` plus `--kv-cache-cold-max-tokens >= --ctx`.

### Measured, with the confound removed [verified]

The originally quoted **1517.4s → 1.4s, "roughly 1000×"** changed two variables at
once: the cache warmed *and* the turn shrank from 320k new tokens to 67. The
ordinary in-RAM live cache produces that turn-2 speedup with no disk cache at all.

Only a **restart** separates them — it empties the live cache, so anything that
survives is the disk. Three arms, same replayed conversation:

| arm | config | cold prefill |
|---|---|---:|
| A | no `--kv-disk-dir` | **370.1 s** |
| C | `--kv-disk-dir`, `cold-max ≥ ctx`, cold start | **376.6 s** |
| D | same as C, **after a server restart** | **38.8 s** |

Arm D's server log shows exactly what happened:

```
kv cache hit text tokens=104944 ... load=162.9 ms
chat ctx=104944..114426:9482  prompt done 38.459s
```

A 104,944-token checkpoint loaded from disk in **163 ms**, leaving only 9,482
tokens to prefill.

**The disk KV cache is real and worth 9.6× on a cold start.** Arm A ≈ arm C
confirms it does nothing on a genuinely cold prompt, as it should. But the
**~1000× headline was inflated roughly 100×** by the confound; the honest figure
for this workload is **9.6×**.

## 2. Background traffic evicts the agent's cache

**[verified — the alias]** · **[unverified — the eviction]**

`ANTHROPIC_SMALL_FAST_MODEL` was set to a "cheaper" model id. `/v1/models`
confirms both ids resolve to one model:

```
ids:            ['deepseek-v4-flash', 'deepseek-v4-pro']
distinct names: {'DeepSeek V4 Flash'}
``` One model, one slot, two
aliases — so Claude Code's background title/summary calls preempted the agent
loop on the same engine.

**Fix:** `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`. On a single-slot server
there is no "cheap" sibling to route to; there is only contention.

Evidence is three adjacent log lines showing alternation. Not yet tested against
the null that the observed alternation was the agent's own divergence.

## 3. The disk cache can starve itself

**[verified — the numbers hold]**

Checkpoints are cumulative full prefixes. The ladder written by one long
conversation can evict the checkpoints that would have prevented the next
re-prefill:

```
18:45:12  kv cache evicted reason=disk-cache-full tokens=163840 hits=0
18:59:39  kv cache evicted reason=disk-cache-full tokens=307200 hits=0
```

**Measured ladder** for one 120,699-token conversation, by listing the directory:

| file | bytes | ≈ tokens | delta |
|---:|---:|---:|---:|
| 1 | 305,964,886 | 21,908 | 21,908 |
| 2 | 587,926,187 | 42,097 | 20,189 |
| 3 | 869,887,377 | 62,286 | 20,189 |
| 4 | 1,151,851,315 | 82,475 | 20,189 |
| 5 | 1,433,821,833 | 102,665 | 20,190 |
| 6 | 1,468,812,441 | 105,171 | 2,505 |

**6 files, 5.4 GiB.**

- **13.64 KiB/token**, from the shutdown checkpoint (1,607.59 MiB / 120,699
  tokens) — the stated 13.5 KiB is right.
- **Checkpoint spacing 20,189 tokens** — the stated ~20,480 is right.
- Scaled to a 320k conversation (files linear, total quadratic): **~16 files,
  ~38 GiB** against the stated ~21 files / ~46 GiB. Same order; the original ran
  slightly higher, plausibly a longer conversation.

⚠️ **A correction issued during verification was itself wrong and is retracted.**
An earlier pass read `KV_CACHE_DEFAULT_CONTINUED_INTERVAL_TOKENS = 10000` aligned
up to 2048 and concluded the interval was **10,240**, not 20,480. That is the
*configured step*, not the realised spacing: `ds4_kvstore_continued_store_target()`
fires only when `live_tokens % step == 0`, and prefill advances in batches that
land on every second multiple. Observed spacing is 20,189. **The original document
was right and the code-derived correction was wrong** — a reminder that reading
the constant is not the same as measuring the behaviour.

**Eviction policy.** The score (`ds4_kvstore.c:532`) is
`(effective_hits + 1.0) × tokens/file_size`, hits decaying on a 6-hour half-life.
Hit-weighting is real but weak; the term that actually kills intermediate rungs is
`kv_cache_incoming_supersedes_continued()`, which multiplies a **never-hit
superseded rung by 0.05**. That is deliberate and correct for append-only growth —
a longer prefix strictly dominates its ancestors — and wrong for a diverging
workload, the same theme as #11.

**Practical:** the cache reached **225 GB** on disk in normal use. Budget
accordingly; 64 GiB is self-defeating.

## 4. Prefix divergence is the actual killer, and caching cannot fix it

**[verified — the conclusion]** · **[unverified — the specific event]**

Tokens after a divergence point have *changed*. Their K/V values have never been
computed in that context. No storage tier substitutes for arithmetic that has not
happened. **Cache design is not the lever; not diverging is.**

Measured on llama.cpp, the divergence sits at **6.5–6.7% depth** — a system
message inserted ~9,700 tokens into a ~150,000-token prompt. An idealised cache
with a snapshot at every token would still re-read 93% of the prompt, so it
recovers almost nothing. The conclusion holds.

⚠️ The original ds4-server event described here diverged at **~29.7% depth**
(token 119,600 of 402,000), which is *not* the same phenomenon as the 6.5% head
insertion #15 identifies. Either the client changed behaviour between sessions or
there are two distinct mechanisms and only one is explained. V4.2 — replay the
same captured requests against both engines — settles it.

## 5. Long prefill collides with client timeouts

**[corrected — the original named the wrong variable]**

Prefill grows with the conversation until it crosses the client's first-byte
budget. The failure mode is not a lost turn: each retry re-sends the same prompt
and re-prefills.

**Measured against a stub that never answers, Claude Code 2.1.228:**

| config | budget |
|---|---:|
| *(default)* | **300.9 s** |
| `CLAUDE_SLOW_FIRST_BYTE_MS=60000` | 300.9 s — **no effect** |
| `CLAUDE_SLOW_FIRST_BYTE_MS=600000` | 300.8 s — **no effect** |
| `API_TIMEOUT_MS=60000` | **60.5 s** — works |
| `API_TIMEOUT_MS=900000` | 301.0 s — cannot raise |

- **The budget defaults to ~301 s, not 1800 s.**
- **`CLAUDE_SLOW_FIRST_BYTE_MS` does not control this abort** in either
  direction. Setting it does nothing.
- **`API_TIMEOUT_MS` behaves as `min(value, ~300 s)`** — it shortens the budget,
  never lengthens it.
- **Exactly 10 retries** (11 POSTs), each byte-identical, then `Request timed
  out`. Backoff is additive and small (300.9 → 335.1 s), not exponential.
  **58 minutes of thrash for one request.**

⚠️ **Caveat.** The stub never sends a byte; `llama-server` does. The case study
contains prefills of **812.7 s that completed successfully**, so a hard 301 s
first-byte cap is not the production failure mode. The likely resolution is that
`server-task.cpp:1360` emits `message_start` when the task is accepted rather
than when generation begins, making the *idle* timeout binding instead. That does
not rescue the recommendation: whatever governs production, it is demonstrably
not `CLAUDE_SLOW_FIRST_BYTE_MS`.

**Completing test:** time the first SSE byte on one streaming request with a
~140k prompt at a cold cache.

## 6. Decode is bandwidth-bound when shallow; at depth it is bound by attention *compute*

**[corrected — the mechanism and the recommendation were both wrong]**

Decode slows dramatically with depth. **Qwen3-Coder-30B-A3B Q8_0, measured
2026-08-12, 3 repetitions:**

| depth | f16 KV | q8_0 KV |
|---:|---:|---:|
| 0 | 63.34 t/s | 61.70 t/s |
| 16,384 | 41.86 | 41.43 |
| 65,536 | 20.21 | 20.65 |
| 131,072 | **12.13** | **12.12** |

**Shallow decode is bandwidth-bound on weights, as claimed [verified].**
63.34 t/s × (3.3B active × 1.06 B/param) = **221 GB/s** effective, matching the
~227 GB/s figure elsewhere in this document.

**The decay at depth is NOT the KV read [refuted].** Halving the KV cache with
`--cache-type-k/v q8_0` changed decode by **0–2% at every depth — nothing.** If the
slowdown were dominated by KV bandwidth, halving the bytes should have roughly
halved the decay. It did not move at all.

The mechanism is attention **compute**: with flash attention the KV is read in
tiles and dequantised on the fly, so q8_0 halves the memory traffic while leaving
the arithmetic identical. Unchanged timing means arithmetic is binding, not bytes.

⚠️ **Therefore `--cache-type-k/v q8_0` is not "the single highest-leverage flag for
long-context decode."** It buys **zero** decode speed. It is a *memory-capacity*
flag — and a very valuable one, since it is the difference between 1M context
fitting on this box and not (#10) — but it should never be recommended for speed.

### KV cost per token by architecture

**[verified from GGUF metadata, except where noted]**

| Model | Layers | KV heads | k/v len | KV/token f16 |
|---|---:|---:|---:|---:|
| Qwen3-Coder-30B | 48 | 4 | 128/128 | **96.0 KiB** |
| gpt-oss-120b | 36 | 8 | 64/64 | 72.0 KiB full → **~36 KiB** (half the layers sliding, window 128) |
| DeepSeek V4 Flash | 43 | **1** | **512/512** | formula gives 86 KiB — **does not apply**, see below |
| GLM-4.5-Air | 46 | 8 | 128 | ~184 KiB *[unverified — model not on disk]* |
| Qwen3-235B-A22B | 94 | 4 | 128 | ~188 KiB *[unverified — model not on disk]* |

**V4's 13.5 KiB/token is empirical, not derived.** Its metadata reports
`head_count_kv = 1` with `key_length = 512`, which is MLA: the cache stores a
compressed latent rather than per-head K and V, and the sparse-attention ratio
reduces it further. The standard `2 × layers × heads × dim × 2` formula gives
86 KiB and is simply the wrong formula. The 13.5 KiB figure comes from measurement
(7.08 GiB at 512k on ds4-server = 14.2 KiB/token), and should be cited that way.

**On a fixed memory budget, attention architecture still decides your maximum
context far more than parameter count does** — that conclusion survives, and it is
what makes V4's 1M context possible at all.

## 7. MXFP4 is the only quant with hardware acceleration on GB10 — on prefill only, and not for free

**[corrected — the original did not bound the scope]**

In `ggml/src/ggml-cuda/mmq.cu:131`:

```c
const bool use_native_fp4 = blackwell_mma_available(cc) &&
    (src0->type == GGML_TYPE_MXFP4 || src0->type == GGML_TYPE_NVFP4);
```

`blackwell_mma_available()` gates on `cc >= BLACKWELL && cc < RUBIN`
(`common.cuh:360`). GB10 reports **12.1**, so it qualifies [verified].

**But that gate governs exactly one compute path: the batched matmul — prefill.**
Decode goes through `mmvq.cu`, which handles MXFP4 with
`vec_dot_mxfp4_q8_1` — a *dequantising* vec-dot with **no Blackwell gate at all**
(`mmvq.cu:19`). There is no native FP4 tensor-core path for decode.

So the bytes-per-parameter argument below stands on its own, but it is a
*bandwidth* argument, not a hardware-acceleration one:

| Format | Bytes/param |
|---|---:|
| fp16 | 2.00 |
| Q8_0 | ~1.06 |
| **MXFP4** | **~0.56** |

### The decode corollary is refuted [measured]

The bytes-per-parameter arithmetic predicts gpt-oss-120b (5.1B active, MXFP4,
~2.9 GB/token) should out-decode Qwen3-Coder-30B (3.3B active, Q8_0,
~3.5 GB/token) by **~1.21×**. Measured at matched shallow depth:

| | decode | effective bandwidth |
|---|---:|---:|
| Qwen3-Coder-30B Q8_0 | **63.34 t/s** | 221 GB/s |
| gpt-oss-120b MXFP4 | **50.21 t/s** | 143 GB/s |

**gpt-oss is 0.79× — slower, not 1.21× faster.** The arithmetic is right; the
conclusion does not follow. MXFP4 achieves only 143 GB/s of effective bandwidth
against Q8_0's 221, because decode has no native FP4 path and pays
`vec_dot_mxfp4_q8_1` dequantisation per byte, where Q8_0 unpacks almost for free.

**"Format beats parameter count here" is false on decode.** Fewer bytes only helps
if you can read them at the same rate, and on this chip MXFP4 cannot.

## 8. There is no universal prefill ceiling — `ubatch` and format each move it ~1.3×

**[verified]**

**All three models, one harness.** `llama-bench`, `-n 0`, 3 repetitions, `-fa on`:

```
    test    ub |   gptoss MXFP4 |  gptoss Q4_K_M |     V4 IQ3_XXS
               |  t/s   TFLOP/s |  t/s   TFLOP/s |  t/s   TFLOP/s
  pp4096  2048 |    2332  23.79 |    1786  18.22 |     473  12.30
 pp16384  2048 |    2187  22.30 |    1704  17.38 |     443  11.52
 pp65536  2048 |    1555  15.86 |    1307  13.33 |     350   9.09
  pp4096   512 |    1801  18.37 |    1265  12.90 |     335   8.70
 pp16384   512 |    1732  17.67 |    1211  12.35 |     318   8.27
 pp65536   512 |    1310  13.37 |     985  10.05 |     267   6.94
```

**Re-measured 2026-08-12 on the same commit: all twelve rows reproduce.** MXFP4
within ±4% (1872.78 / 1718.07 / 1357.88 at ub512; 2355.89 / 2234.24 / 1611.47 at
ub2048); Q4_K_M within ±1–7% (1275.60 / 1213.43 / 997.50 and 1807.27 / 1726.79 /
1338.31).

gpt-oss Q4_K_M reaches 12.35–12.90 TFLOP/s at `ub=512` — a conventional dequant
format, well clear of the 8 TFLOP/s that once looked like a hardware ceiling.
There is no ceiling; two dequant-heavy models simply landed near each other at
the default ubatch.

**The harness transfers to production.** A same-depth, same-ubatch check against
live `llama-server` agreed closely.

**Measured against production [verified].** Same model, same settings
(262k ctx, `ub 2048`, q8_0 KV):

| | t/s |
|---|---:|
| `llama-bench` pp131072 | **271.49 ± 0.27** |
| production, 138,595 tok | 263.0 |
| production, 142,981 tok | 259.2 |
| production, 149,679 tok | 253.5 |
| production, 150,072 tok | 253.2 |

At the closest comparable depth that is a **3.2% gap**, with production slightly
slower — as expected, since it is deeper *and* pays real HTTP, jinja templating
and tokenisation. Every production point sits 3–7% under the bench figure,
decreasing monotonically with depth. `llama-bench pp65536 = 350.31` also
reproduces the published 350 t/s almost exactly.

**So the claim transfers; the precision does not.** The originally quoted
agreement — 349.63 predicted vs 349.69 observed — is coincidence. The same
`pp4096 ub512` row across four independent process launches spans **4.3%**
(1795.72 / 1800.58 / 1859.99 / 1872.78) while `llama-bench`'s own reported ±
within a run is 0.1–0.7%: **the harness understates its own variance by 4–6×**.
Four-significant-figure agreement is ~200× tighter than the instrument can
resolve, and it was measured at *different* depths (65,536 vs 62,903) besides.
The honest statement is "within a few percent, bench slightly optimistic".

**Practical rule: treat any bench difference under ~5% as noise**, quote the
between-launch spread rather than `llama-bench`'s ±, and interleave arms
(A/B/A/B) rather than running them in sequence.

### What actually moves prefill

**1. `ubatch` — free, and the largest single lever** (see #12).
**2. Format — controlled, and real** (see #13): MXFP4 vs Q4_K_M, 1.19–1.43×.
**3. Architecture — uncontrolled.** V4 sits ~40% below gpt-oss Q4_K_M even after
normalising for active parameters. Plausible causes: 284B total parameters means
far heavier MoE expert-gather traffic; the compressed-attention indexer adds work
the active-parameter count does not capture; IQ3_XXS uses lookup-table
dequantisation. **Not separated by these experiments and not claimed to be.**

### Caveat on the metric

"Effective TFLOP/s" is `2 × active_params × t/s` — a **derived proxy**, not a
measured FLOP count. Sound for comparing one model against itself across formats
or ubatch sizes. Across architectures it silently assumes the active-parameter
figure captures all the work, which for V4's indexer and heavy expert gather it
does not. **Cross-model rows are indicative; same-model rows are evidence.**

## 9. gpt-oss-120b cannot be stretched past 131k

**[verified — code behaviour and magnitude]**

Upstream config:

```json
"rope_scaling": {"rope_type":"yarn","factor":32.0,
                 "original_max_position_embeddings":4096}
```

4096 × 32 = 131,072. Its window is *already* the YaRN-extended one; asking for
more stacks a second YaRN on the first.

**The trap is real and confirmed in source.** `server-context.cpp:1311-1313` caps
`n_ctx_slot` back to `n_ctx_train` with only a warning, while
`llama-context.cpp:130-132` resolves `n_ctx` and the rope parameters from
**independent ternaries**:

```c
cparams.n_ctx           = params.n_ctx           == 0    ? hparams.n_ctx_train          : params.n_ctx;
cparams.rope_freq_base  = params.rope_freq_base  == 0.0f ? hparams.rope_freq_base_train : params.rope_freq_base;
cparams.rope_freq_scale = params.rope_freq_scale == 0.0f ? hparams.rope_freq_scale_train: params.rope_freq_scale;
```

Nothing resets the rope parameters when the context is capped. The server looks
fine and the positional encoding is silently wrong. Also: `--cache-reuse` is
disabled automatically under sliding-window attention (logged, easy to miss).

**The generalisable rule: run at the vendor's declared
`max_position_embeddings` and never pass rope flags yourself.**

### Measured: the corruption is real, and severe [verified]

gpt-oss-120b MXFP4, one chunk at the model's full **131,072** context, the rope
flag as the only variable:

| arm | PPL |
|---|---:|
| vendor config, no rope flags | **2.7940 ± 0.02197** |
| `--rope-scaling yarn --rope-scale 2` | **94.4541 ± 1.17464** |

**A 34× degradation.** Perplexity 94 is a model emitting near-noise. Passing rope
flags on top of a config that already carries YaRN does not merely "get worse" —
it destroys the model's output, silently, while the server reports healthy.

**The corruption is invisible at short context.** The same comparison at 2048:

| context | no flags | `--rope-scale 2` | effect |
|---:|---:|---:|---|
| 2,048 | 4.7195 | 4.5520 | 3.5% *better* |
| 131,072 | 2.7940 | **94.4541** | **34× worse** |

At 2048 the flag maps positions 0–2047 onto 0–1023, deep inside trained range —
harmless, even marginally helpful. At 131,072 it maps them onto 0–65,535, halving
the angular spacing across the whole operating range, and the encoding collapses.
Perplexity here is bit-exact deterministic, so both numbers are the flag's doing
and nothing else.

**Anyone testing this at a convenient short context will conclude the flags are
harmless.** They are not. The test has to run at the ceiling.

**One narrowing on the capping half:** it is `llama-server`-specific
(`server-context.cpp:1311-1313`). `llama-perplexity` at `-c 262144` only warns —
`n_ctx_seq (262144) > n_ctx_train (131072) -- possible training context overflow`
— and proceeds at the requested size.

### On rope scaling generally

The ivory-tower ideal is a model trained natively at the target length: RoPE has
a fixed angular budget, and YaRN packs more positions into a budget sized for
fewer. Training on the stretched ruler teaches the model to read it, but where
two positions land on nearly identical angles, no amount of training separates
them — the information is not in the encoding. YaRN is deliberate about where it
spends that loss (`beta_fast`/`beta_slow` ramp between leaving high-frequency
dims nearly untouched and compressing the low-frequency, long-range ones).

Native training at 1M does not exist, and not by oversight: attention is O(n²),
and there are not enough genuine million-token documents to train on. Every
long-context model is extended in stages; "native" is a spectrum, not a binary.

### E5 — the tolerance threshold is not a stretch factor [verified]

Qwen3-Coder-30B, one variable per pass, each depth against its own control:

| depth | x1.25 | x1.5 | x2.0 | x4.0 |
|---|---:|---:|---:|---:|
| 8,192 | −0.89% | −1.53% | −2.12% | **−3.17%** |
| 32,768 | −0.03% | +0.01% | +0.19% | +0.83% |
| 131,072 | −0.18% | −0.09% | −0.01% | **+2.39%** |

**The worst point across 15 passes is +2.39%.** The same flag on gpt-oss at its
ceiling gave **+3,281%**. And ×4.0 *improves* Qwen by 3.17% at 8,192 while costing
2.39% at 131,072 — same model, same corpus, opposite sign.

**The mechanism is mismatch, not extrapolation.** `--rope-scale N` divides
positions by N: it compresses the angular range and never pushes past the trained
limit. The damage is the distance between the mapping applied at inference and the
one the model learned. Qwen ships no vendor YaRN, so ×2 is a small perturbation of
a mapping learned at ×1. gpt-oss ships factor 32, so ×2 gives an effective ×64 and
every position lands at an angle it never saw.

⚠️ **262,144 is unreachable on this box.** `llama-perplexity` holds
`n_ctx × n_vocab × 4` bytes of logits; at Qwen's 151,936 vocab that is 148.4 GiB,
against 74.2 GiB at 131,072. So Qwen was tested at *half* its native window, and a
stretch at its true ceiling remains untested.

**[verified — the direction]** The comparable numbers for model selection are
therefore *base length* and *stretch factor*, not the presence of scaling:

| Model | Base | Factor | Result |
|---|---:|---:|---|
| DeepSeek V4 Flash | 65,536 | ×16 | 1M |
| gpt-oss-120b | 4,096 | ×32 | 131k |

Whether that translates into measurably better long-context fidelity is
**untested** — E5. gpt-oss was rejected here for its **context ceiling**, not its
quality; its output was never evaluated.

## 10. llama.cpp beats the purpose-built engine for DeepSeek V4

**[unverified — the comparison is uncontrolled]**

llama.cpp implements `deepseek4` with the real compressed attention
(`INDEXER_TOP_K`, `COMPRESS_RATIOS`, sliding window), so the cheap KV survives —
and unlike `ds4-server` it can quantize the KV cache. That single capability is
the difference between 1M context fitting and not.

| | ds4-server | llama.cpp |
|---|---:|---:|
| Quant | q2 (~2.3 bpw) | **UD-IQ3_XXS (~3.06 bpw)** |
| Context | 512k (1M refused) | **1M** |
| Weights | 80.8 GiB | 95.9 GiB |
| KV | 7.1 GiB (f16 only) | **7.2 GiB @ 1M (q8_0)** |
| Total RAM | ~92 GiB @512k | **~106 GiB @1M** |
| Decode | 13.5 t/s | **16.3 t/s** |
| Prefill | 335 t/s | 300 t/s |

⚠️ **Quant, KV type and context all differ, so this is not a controlled
comparison.** A larger model decoding *faster* is surprising and deserves
re-measurement at matched settings (V10.1). Note also that `335 t/s` appears here
as ds4-server's prefill *and* in #8's matrix as llama.cpp's V4 `pp4096 @ ub512` —
one attribution is likely transposed.

The KV-quantisation capability is reason enough to prefer llama.cpp regardless;
that part does not depend on the contested rows.

**Verified:** `n_ctx_slot = 1048576`, no capping; 106 of 121 GB resident under
`mlock`; `/v1/messages` returns native `thinking` blocks; a generated SWAR
`popcount64` compiled clean under `-Wall -Wextra` and matched
`__builtin_popcountll` on all test cases.

### Throughput vs depth — DeepSeek-V4-Flash UD-IQ3_XXS, 1M ctx, q8_0 KV

| Prompt depth | Prefill | Decode |
|---:|---:|---:|
| ~0 (43 tok) | — | **16.30 t/s** |
| 116k (complete) | **210.5 t/s** | **12.44 t/s** |

Both curves decay with depth: prefill attention is superlinear in context, and
decode must re-read a KV cache that grows every token (#6).

Note the caveat on the shallow decode figure: 276 of 517 tokens in that smoke
test were `thinking` blocks. V4 Flash is a reasoning model, so a substantial and
variable fraction of every response is deliberation the user never sees. **n=1 —
do not treat that ratio as a rate** (V14.2).

## 11. Prefix caching assumes append-only growth; coding agents are not append-only

**[verified]**

Two different things get called "the KV cache", and only one of them is a
questionable fit here.

**Within a generation**, the KV cache is load-bearing and not optional. Without
it, producing token N re-derives K/V for all N−1 predecessors on every step.

**Across requests**, prefix caching bets on *append-only* growth — the ChatGPT
shape. A coding agent is not that shape. It front-loads a large context, then
rewrites it at structurally meaningful moments: plan mode → execution, subagent
spawn and return, compaction, tool-result trimming.

**The payoff is bimodal, not average — verified on two independent sessions.**
Reuse fraction across 31 tasks:

```
   0-  9%  #########  9
  10- 19%  #  1
  20- 29%  .  0
     …            (nothing in the middle)
  80- 89%  #  1
  90- 99%  ###################  19
```

Prefix caching is worth roughly **9× while the prefix holds, and exactly nothing
across a break.** Whether it "makes sense" depends entirely on divergence
frequency, which is a property of the *client*, not the server.

**`--cache-reuse` is unavailable on DeepSeek V4** — `llama_kv_cache_dsv4::
get_can_shift()` returns false unconditionally (`llama-kv-cache-dsv4.cpp:1394`),
so `llama_memory_can_shift()` is false and the server silently zeroes
`n_cache_reuse` (`server-context.cpp:1278-1291`).

**The tension worth naming:** V4's compressed rows are simultaneously why 512k of
KV fits in 7 GiB (#6) *and* why positions are block-derived and cannot be shifted.
**The architectural feature that buys the context is the feature that blocks the
cache repair.**

## 12. `--ubatch-size 2048` buys 19–30% of prefill, and 2048 is the optimum

**[verified — reproduced, and 2048 confirmed optimal]** · **[unverified — the memory margin]**

`n_ubatch` defaults to 512, which caps arithmetic intensity: each micro-batch
re-reads weights that could have been amortised over more tokens.

**Same model, same harness, one variable** (gpt-oss-120b MXFP4, 3 repetitions):

| Prompt depth | published gain | re-measured 2026-08-12 |
|---|---:|---:|
| 4,096 | +29.5% | **+25.8%** |
| 16,384 | +26.2% | **+30.0%** |
| 65,536 | +18.7% | **+18.7%** |

**Confirmed in production.** Applied to the live 1M-context V4 server, a
62,903-token prompt ran at 349.69 t/s against 266.94 at `ub=512` — **+31.0%**.
The `ub=2048` session averaged **275.5 t/s** across a whole agentic session
against the case study's 194.9 at `ub=512`.

**Cost: ~6 GB of compute buffer.** At 1M context the V4 server went from 106 GB
resident to **112 of 121 GB**. It loads and runs, but the margin is thin —
`DS_UBATCH=512` reverts if a future config OOMs on load.

⚠️ 2048 is the largest value tried, not a demonstrated optimum, and "free" is
true only if the memory margin survives a worst-case request (V12.2, V12.3).

## 13. The native FP4 path is worth 1.16–1.34×, costs 6.4% perplexity, and is largely unreachable on V4

**[verified — measurement, attribution and cost]**

**The controlled experiment.** One model (gpt-oss-120b), one harness, one
architecture, 5.1B active either way. The MXFP4 file was requantised in place to
Q4_K_M so that **format is the only variable**:

| Test | ub | MXFP4 | Q4_K_M | Ratio |
|---|---:|---:|---:|---:|
| pp4096 | 2048 | 2332 t/s | 1786 t/s | **1.31×** |
| pp16384 | 2048 | 2187 t/s | 1704 t/s | 1.28× |
| pp65536 | 2048 | 1555 t/s | 1307 t/s | 1.19× |
| pp4096 | 512 | 1801 t/s | 1265 t/s | **1.43×** |
| pp16384 | 512 | 1732 t/s | 1211 t/s | 1.43× |
| pp65536 | 512 | 1310 t/s | 985 t/s | 1.33× |

**Re-measured 2026-08-12, same commit, full matrix — the ratios hold:**

| Test | ub | ratio (published) | ratio (re-measured) |
|---|---:|---:|---:|
| pp4096 | 2048 | 1.31× | **1.30×** |
| pp16384 | 2048 | 1.28× | **1.29×** |
| pp65536 | 2048 | 1.19× | **1.20×** |
| pp4096 | 512 | 1.43× | **1.47×** |
| pp16384 | 512 | 1.43× | **1.42×** |
| pp65536 | 512 | 1.33× | **1.36×** |

They stack: MXFP4 at `ub 2048` is **1.847×** over Q4_K_M at `ub 512` (2355.89 vs
1275.60), matching the originally reported 1.84×.

Note the ubatch lever is *larger* for the dequant format — Q4_K_M gains
**+41.7% / +42.3% / +34.2%** from `ub 2048` against MXFP4's +25.8% / +30.0% /
+18.7%, which is what an arithmetic-intensity explanation predicts: the format
that pays more per weight-read benefits more from amortising it.

The advantage is largest at small ubatch and shallow depth — where
matrix-multiply dominates and attention does not — which is what a
dequantisation-avoidance explanation predicts.

### The attribution, decomposed [verified]

MXFP4 differs from Q4_K_M in *two* ways: it takes the native path **and** it is
59.0 GiB against 81.8. Separating them needs a build with Blackwell MMA suppressed
on **both** host and device (`-DGGML_NO_BLACKWELL_MMA`, `common.cuh:286` and
`:360`), so the two selectors cannot desynchronise.

**Q4_K_M is the control** — it never enters the FP4 branch, so the flag must be a
no-op for it, and is: 1275.60 → 1296.95, 997.50 → 1007.23, 1807.27 → 1819.86 t/s,
all inside the 4% noise floor. MXFP4 meanwhile slows 15–24%.

| test | MXFP4/Q4_K_M pristine | ablated | native path worth |
|---|---:|---:|---:|
| pp4096 ub512 | 1.468× | 1.096× | **1.34×** |
| pp65536 ub512 | 1.361× | 1.109× | **1.23×** |
| pp4096 ub2048 | 1.304× | 1.059× | **1.23×** |
| pp65536 ub2048 | 1.204× | 1.037× | **1.16×** |

**The native FP4 path is worth 1.16–1.34×. Fewer bytes and cheaper unpacking are
worth only 1.04–1.11×.** So the hardware attribution is right in direction — the
tensor-core path is the dominant term — but the originally quoted 1.19–1.43× is
the *combined* effect, not the path's contribution.

### ⚠️ It is not free: the native path costs 6.4% perplexity

| | PPL |
|---|---:|
| native FP4 path (default) | **8.0227** |
| dequant path (ablated) | **7.5423** |

`use_native_fp4` selects `block_fp4_mmq` for the **activations** — 4-bit — where
the dequant route uses `block_q8_1_mmq` — 8-bit. Turning the path off makes the
model measurably *more accurate*.

Both #7 and #13 present native FP4 as a pure win. **It is a speed/accuracy trade,
and the accuracy side was never measured.** Whether 1.16–1.34× of prefill is worth
6.4% of perplexity is a judgement, but it should be made knowingly.

**Honest limit:** the branch bundles Blackwell FP4 MMA *and* 4-bit activations, so
this cannot prove the tensor cores specifically account for the 1.16–1.34×.
Separating them would need a build keeping FP4 MMA with 8-bit activations, which
the code does not support.

### What this means for a custom quant

**[verified — from V4's actual tensor list]** V4 Flash UD-IQ3_XXS is 284.3B
parameters in 94.6 GiB: 63.4% IQ2_S, 31.0% IQ3_XXS, and already 1.5% MXFP4. A
pure MXFP4 build would be **140.7 GiB** and does not fit in 121 GB.

Inside a realistic 106 GiB weight budget, with the remainder pinned at the IQ2_S
floor, **only 40.1% of parameters can be promoted to MXFP4**:

| native-path speedup on the promoted portion | overall gain |
|---|---:|
| 1.19× | **+6.8%** |
| 1.31× | **+10.5%** |
| 1.43× | **+13.7%** |

| Lever | Prefill gain | Cost |
|---|---:|---|
| `-ub 2048` | **+31%** | **one flag, already applied** |
| Custom hybrid MXFP4 | **+7 to +14%** | 144 GiB download, imatrix (days), requantise, eval |

**The custom-quant project is not worth doing.** The free flag delivers more than
the weeks of work would.

⚠️ **And that conclusion inverts if V7.1 refutes the tensor-core attribution.** If
MXFP4 is fast because it is *smaller*, then promoting IQ2_S tensors (2.5 bpw) to
MXFP4 (4.25 bpw) makes them larger — slower, not faster. The project would not be
marginal; it would be backwards.

## 14. Output tokens cost ~17× more than input tokens here

**[corrected — the original quoted a depth-mismatched ratio]**

A direct consequence of the batching asymmetry. **At matched depth (~116k):**

| | Rate | Relative cost |
|---|---:|---:|
| Reading input (prefill) | 210.5 t/s | 1× |
| Writing output (decode) | 12.44 t/s | **~17×** |

The original also quoted **~38×**, obtained by dividing *shallow* prefill
(473 t/s) by *deep* decode (12.45 t/s). Those are different depths and the ratio
is not meaningful. **Use 17×.** The claim that improving prefill "widens the gap"
rested on the 38× figure and should be dropped.

**Why it still matters.** V4 Flash is a reasoning model, so a large fraction of
every response is deliberation the user never sees. This inverts a habit carried
over from hosted models, where input is the thing you economise:

- Terser system prompts help twice — less to read, and less to imitate
- Lower reasoning effort where a task does not need deliberation
- Asking for code rather than code-plus-explanation

**Keep the magnitude honest.** Decode was 11.1 of 84.5 minutes in the case study.
Halving thinking output saves ~5 minutes. Redundant prefill was 57.9. This is a
real lever and a small one.

## 15. A trailing system message rewrites the *head* of the prompt

**[verified — mechanism, magnitude and fix]**

The single largest cost in this document (#4, #11, and 68.6% of measured model
time in the case study) has one cause.

**Claude Code appends ephemeral `system`-role messages to the END of the
`messages` array.** DeepSeek V4's chat template **hoists every system message to
the TOP** of the rendered prompt (template lines 33–67: collect into
`ns.system_prompt`, append the tools block, emit before any turn).

So appending one short system message changes the rendered prompt **~9,700 tokens
in — 6.5% of the way through** — instead of at the end where it was written.

**Measured at token level on 13 captured requests**, rendering each through
`/apply-template` and `/tokenize`:

| pair | common prefix | depth | re-read |
|---|---:|---:|---:|
| #2→#3 | 9,595 | 6.7% | 133,386 |
| #7→#8 | 9,734 | 6.5% | 139,945 |
| #8→#9 | 9,838 | 6.6% | 140,234 |

Every request ending in a system message re-read everything; every request ending
in a user message reused the cache. No exceptions across 13 requests.

**It is an insertion, not a rewrite.** The post-divergence content survives
**100% verbatim**, relocated by only 104–234 tokens.

**And the server reuses none of it.** All three requests prefilled their *entire*
prompt at **0.0% reuse** despite the available 9,700-token common prefix. See #16
for why.

### The fix, measured

Rendering system messages that appear after the prompt preamble **in place**
rather than hoisting them makes them append-only and preserves the prefix.
`llama-server --chat-template-file` takes the override; no code change.

| | prefilled | wall |
|---|---:|---:|
| stock | 591,519 tok | **38.8 min** |
| patched | 154,705 tok | **10.5 min** |

**96.4% of redundant prefill removed.** Per request: #8 went 149,679 tok /
590.4 s → **1,149 tok / 7.8 s**; #9 went 150,072 / 592.8 s → **396 / 3.7 s**.

Template at `verify/templates/dsv4-inline-assistant.jinja`; it keeps the
preamble hoisted until the model first speaks, so only mid-conversation reminders
move.

### The quality gate is passed — ship it [verified]

Ten real closed issues, each with a known-good patch, scored fail-then-pass on
the project's own gate (transpile + match `.expected.*` + gcc + cppcheck +
clang-tidy + MISRA). Claude Code driving this server, editing the repo with tools
— the actual workload, not a prompt comparison.

| | stock | patched |
|---|---:|---:|
| **solved** | **4/10** | **10/10** |
| prefill tokens | 15,341,796 | **1,877,020** (8.2× less) |
| prefill **per turn** | 34,789 | **2,005** (**17× less**) |
| turns | 441 | 936 |
| wall clock | 14.3 h | **8.6 h** |
| timed out (90 min cap) | **9/10** | 2/10 |

**The patched template solved every task, including all six stock failed, in 40%
less wall-clock.** The concern that inline reminders might be weighted differently
and hurt behaviour is not supported: it is better on every axis measured.

Prefill *per turn* is the cleanest figure here — normalised for how much work each
arm did, so it is not confounded by turn count. Stock burns ~35k tokens of
redundant re-reading on every single turn.

⚠️ **Stock's 4/10 is a lower bound.** Nine of ten hit the 90-minute cap, so with
unlimited time it would solve more. The supported claim is *"under a fixed time
budget, patched solves 2.5× as many"*, not that the template makes the model
smarter. Two cases resist even that reading — on #1094 stock spent 43 turns and
failed where patched needed 34, and on #1037 stock spent 50 where patched needed
26 — but n=2 is not a mechanism.

⚠️ One anomaly: **#1012** is the only task where stock was cheaper (50 min, no
timeout) while patched took the full 90 and burned 750k prefill, 4× its own
average. Both solved it. Unexplained.

### Generality — narrower than it looks [verified against two other templates]

The conditional holds — *any* template that hoists system messages will do this —
but the population of such templates is small. Comparing the three models on this
box:

| model | `messages[0]` system | later system messages | consequence |
|---|---|---|---|
| **DeepSeek V4** | all collected into `ns.system_prompt` | **hoisted to the head** | prefix cache destroyed |
| **Qwen3-Coder** | `system_message`, rest `messages[1:]` | **rendered in place** | append-only, no problem |
| **gpt-oss** | `developer_message`, rest `messages[1:]` | **silently dropped** | content loss |

Qwen's turn loop renders a later system message where the client put it:

```jinja
{%- elif message.role == "user" or message.role == "system" or message.role == "assistant" %}
    {{- '<|im_start|>' + message.role + '\n' + message.content + '<|im_end|>' + '\n' }}
```

**So V4's template is the outlier, and the fix in this document makes V4 behave
exactly like Qwen already does.** That is the strongest argument that in-place
rendering is correct behaviour rather than a workaround — it is the mainstream
convention, and Qwen has no cache problem precisely because it follows it.

**gpt-oss has a different latent bug.** Its turn loop branches on
`assistant`/`tool`/`user` and then ends — no `system` branch, no `else`. A
mid-conversation system message hits nothing and is **silently dropped**. Sending
Claude Code's reminders to a gpt-oss server means the model never sees them: a
correctness failure rather than a performance one, and equally silent.

⚠️ Still tested on one captured session, in "learning" output style with a 35 KB
`SessionStart` hook. Generality across *output styles* remains untested; what is
now established is generality across *templates*.

## 16. One hardcoded `return 0` costs ~29,000 tokens per session

**[verified]**

When the head changes, the server does not reuse the ~9,700-token prefix it
still has. It resets to zero. `llama-model.cpp:2506-2512`:

```c
int32_t llama_model_n_swa(const llama_model * model) {
    // dsv4 kv-cache has SWA but it cannot be used as a rollback because of
    // other compression ratios, so we return 0 here
    if (model->arch == LLM_ARCH_DEEPSEEK4) {
        return 0;
    }
    return model->hparams.n_swa;
}
```

That single return does three things at once:

1. **Disables `--swa-full`.** `server-context.cpp:1296-1299` gates the rejection
   on `llama_model_n_swa() == 0`. The server logs `swa_full is not supported by
   this model, it will be disabled`.
2. **Makes the reuse threshold maximally strict.** `server-context.cpp:3299`
   computes `pos_min_thold = pos_next - n_swa - …`; with `n_swa = 0` the
   threshold is `pos_next` itself — *stricter* than the real 128-token window.
3. **Blocks context-checkpoint creation**, which requires
   `seq_rm_type ∈ {FULL, RS} || n_swa > 0` (`server-context.cpp:3468-3475`), so
   the checkpoint search falls through to `do_reset` → `n_past = 0`.

**The reset is not caused by the sliding window being small. It is caused by the
server being told there is no window at all** — which removes both the workaround
flag and the checkpoint fallback that would have covered it.

Worth ~29,000 tokens per session. Small beside #15's 436,814, but it is a
one-line upstream diagnosis that, unlike the abandoned cache-shifting work,
requires no new compressed-cache code. Also worth reporting upstream:
`llama_kv_cache_iswa` logs `using full-size SWA cache` *before* the server
disables the flag — the memory appears to be allocated and the benefit discarded.

---

## Case study: one real agentic session

**[verified — every figure reproduces from the raw log]**

A `/pr-check` skill run against a real open PR on a TypeScript compiler project
(`jlaustill/c-next` #1140). DeepSeek-V4-Flash UD-IQ3_XXS, 1M ctx, q8_0 KV, driven
by Claude Code over `/v1/messages`.

```
DECODE   (writing output)     11.1 min      8,280 tok   12.45 t/s   13.1 %
PREFILL  (reading input)      73.4 min    858,025 tok   194.9 t/s
  necessary                   15.5 min    180,812 tok               18.3 %
  REDUNDANT                   57.9 min    677,213 tok               68.6 %
TOTAL model time              84.5 min
```

| Prefill events | Count |
|---|---:|
| Full re-reads (>20k tokens) | **6** |
| Incremental (<20k tokens) | 21 |
| Largest single prefill | 154,431 tok |

Computed by summing real per-task millisecond timings, not tokens ÷ an average
rate — prefill rate varies 190–210 t/s with depth, so the two methods are not
interchangeable.

**68.6% of this machine's working life was spent re-reading context it had
already read.** Decode accounted for 13%.

⚠️ `necessary` is a **lower bound** — defined as the largest single prefill plus
the sum of all incrementals, which *assumes every full re-read after the first
was avoidable*. #15 shows most were. VC.1 classifies each one by measured cause.

**The two kinds of optimisation this separates:**

- **Faster prefill** — ubatch, format. Scales all 73.4 minutes.
- **Less prefill** — #15. Only this touches the 57.9 minutes of waste.

They multiply rather than compete.

---

## Practical gotchas

- **`sudo` scripts fail silently** when launched through a non-interactive
  wrapper — the password prompt has no TTY. Run them in a real terminal.
- **`grep` needs `--line-buffered`** when following a log, or a low-volume stream
  looks dead for minutes.
- **`--load-mode mlock` needs `LimitMEMLOCK=infinity`** in the systemd unit.
- **`llama-server` binds its chat template at startup.** `/apply-template`
  silently ignores a `chat_template` in the request body, so a per-request
  template A/B returns two identical streams and reads as "the patch changed
  nothing". A template A/B needs a second server with `--chat-template-file`.
- **`dsv4-proxy` has `Requires=dsv4-server`.** Stopping the server stops the
  proxy; starting the server does *not* bring it back.
- **"DSpark" is taken** — it is DeepSeek's own speculative draft head
  (`markov_head`, `confidence_head`), not anything to do with DGX Spark.

## Reproduction

Server and build scripts live in `/home/linux`: `build-llamacpp.sh`,
`dsv4-server.sh`, `qwen-server.sh`, `gptoss-server.sh`, `install-*.sh`,
`cleanup-models.sh`.

Verification harness, per-test results and raw logs live in `/home/linux/verify`.
Methodology, falsified assumptions and the full test log are in
`NOTES.md`. The pre-verification version of this document is preserved
as `spark-cc-finding.ORIGINAL-20260812.md`.

⚠️ `build-llamacpp.sh` runs `git pull --ff-only`. Every number here is on commit
`687e778`; running that script moves the checkout and invalidates comparability.
