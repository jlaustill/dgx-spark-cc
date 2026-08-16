# Running Claude Code against local models on a DGX Spark

Working notes. Everything here was measured on one machine over 2026-08-08/10.
Claims are tagged **[measured]**, **[derived]** (arithmetic on measured values), or
**[hypothesis]** (untested).

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
and runs straight into the wall. Same model, same memory, **473 t/s versus
12 t/s**.

## Open experiments (TODO)

Working queue. Ordered by value ÷ cost, not by finding number.

| # | Question | Experiment | Cost | Status |
|---|---|---|---|---|
| **E1** | What rewrites history mid-conversation? (#4, #11) | Dump-proxy captured request bodies; correlated with server reuse. | done | ✅ **ANSWERED — trailing system messages are hoisted to the prompt head. See #15** |
| **E2** | Does larger `--ubatch-size` help prefill? (#8) | `llama-bench` sweep of `-ub`. | ~1 h | ✅ **answered — see #12** |
| **E3** | Does the native FP4 path beat a dequant format? (#7, #8) | Same model, two formats, one harness. | done | ✅ **answered — no ceiling existed; format worth 1.19–1.43×. See #8, #13** |
| **E4** | Can V4 Flash *write* a fix, not just analyse one? (case study) | Regression-test-first on issue #1139. A test it wrote that fails, then passes, is unambiguous; a patch that merely looks right is not. | 1 session | **open** |
| **E7** | Does an in-place system-message template fix the invalidation without hurting output? (#15) | Override with `--chat-template`, rendering post-first-user system messages inline. Measure reuse rate AND output quality. | ~1 day | **open — highest value** |
| **E5** | Where is the rope-stretch tolerance threshold? (#9) | One model, identical prompts, native window vs ×2 YaRN. Qwen3-Coder-30B at 262k vs 524k. Same weights, one variable. | 1 download + harness | **open** |
| ~~**E6**~~ | ~~DSV4 compressed-cache shifting~~ (#11) | — | weeks | ❌ **DROPPED — E1 shows the change is at token 0; shifting cannot help (#15)** |

**Everything here targets prefill, which is where the time goes.** The case study
measured 73.4 min of prefill against 11.1 min of decode, and prefill splits in
two:

| Component | Measured | Share | Attacked by |
|---|---:|---:|---|
| Necessary prefill | 15.5 min | 18.3 % | E2, E3 ✅ — up to ~1.4× faster |
| **Redundant prefill** (6 divergences) | **57.9 min** | **68.6 %** | **E1 ✅ diagnosed → E7** — make it unnecessary |
| Decode | 11.1 min | 13.1 % | *nothing here* |

These are complementary and multiply: eliminating the divergences *and* doubling
throughput would take 73.4 min to roughly 8. E4 and E5 are quality experiments
and affect neither.

**Where things stand.** E1, E2 and E3 are answered. `-ub 2048` is a free +31–41%
on V4 prefill, already applied (#12). The native FP4 path is worth a further
1.19–1.43× (#13) but needs a custom hybrid quant to capture on V4 — weeks for a
fraction of that gain. **E1 found the real cause of the 68.6% waste: Claude Code
appends system messages to the tail, and the chat template hoists them to the
head, invalidating the whole prefix (#15).** E6 is dropped as a result. The
remaining work is E7 — patch the template — plus the quality experiments E4/E5.

**Prerequisite for E4 and E5:** a repeatable eval. Without pass/fail criteria,
"acceptable coding results" is unfalsifiable and the results are not publishable.
Minimum viable: 10–20 real issues with known-good patches, scored on *compiles*
and *fixes the issue*.

---

## Terminology

Two phases, and the split within one of them that turns out to matter most.

| Term | What the model is doing | llama.cpp log label | Bound by |
|---|---|---|---|
| **Prefill** | *Reading* input tokens, building KV | `prompt eval time` | compute — parallel across tokens |
| **Decode** | *Writing* output tokens, one at a time | `eval time` | memory bandwidth — serial |

Naming trap: bare **`eval time` is decode**; `prompt eval time` is prefill. They
sit adjacent in the log and are trivially easy to swap. `llama-bench` calls them
`tg` and `pp` respectively.

Prefill then splits:

| Term | Meaning |
|---|---|
| **Necessary prefill** | The irreducible minimum — one pass over the context, plus the genuinely new tokens each turn adds |
| **Redundant prefill** | Re-reading tokens already processed, because cache invalidation threw the work away |

Redundant prefill is the quantity this document is ultimately about. It is
invisible in any single request — every prefill looks legitimate on its own — and
only appears when you sum a whole session.

---

## The machine

| | |
|---|---|
| Host | `gx10-52c8`, NVIDIA DGX Spark (GB10) |
| Compute capability | **12.1** (Blackwell) |
| Memory | 121 GB unified LPDDR5X, ~273 GB/s theoretical |
| Measured effective bandwidth | **~227 GB/s** [derived, see #6] |
| Arch / toolchain | aarch64, CUDA 13.0, gcc 13.3 |
| Storage | NVMe, ~3.7 GB/s observed writes |

Client is a separate machine on the LAN running Claude Code with
`ANTHROPIC_BASE_URL` pointed at the Spark.

---

## 1. A default that silently disables the disk KV cache

`ds4-server` (antirez's DwarfStar engine) can persist KV checkpoints to disk, but
two things must both be true and only one is obvious:

```
--kv-disk-dir DIR                 # off by default
--kv-cache-cold-max-tokens N      # DEFAULT 30000
```

The second is the trap. Real coding-agent prompts here run 75k–400k tokens, so
with the default nothing is ever checkpointed even after enabling the directory.

**Symptom:** every single turn logged a full cache miss.

```
live kv cache miss live=321864 prompt=325568 common=1 reason=token-mismatch
```

82 requests in 24h, 82 misses, zero hits. Every turn re-prefilled the entire
conversation.

**Fix:** `--kv-disk-dir` plus `--kv-cache-cold-max-tokens >= --ctx`.

**Result [measured]:** same conversation, before and after the cache warmed:

```
prompt done 1517.418s   ← cold, 319,909 tokens
prompt done    7.018s
prompt done    1.886s
prompt done    1.394s   ← 67 new tokens on a 321k prefix
```

**25 minutes → 1.4 seconds.** Roughly 1000× on time-to-first-token.

---

## 2. Background traffic evicts the agent's cache

`ANTHROPIC_SMALL_FAST_MODEL` was set to a "cheaper" model id. But `/v1/models`
reported both ids resolving to the same weights:

```json
{"id":"deepseek-v4-flash", "name":"DeepSeek V4 Flash"}
{"id":"deepseek-v4-pro",   "name":"DeepSeek V4 Flash"}
```

One model, one slot, two aliases. So Claude Code's background title/summary calls
were preempting the agent loop on the same engine and evicting its KV on the way
in and out — visible as strict alternation, to the second:

```
15:44:08  TOOLS prompt done 226.382s
15:44:08  TOOLS stream closed during prefill
15:44:08  live kv cache miss live=75763 prompt=14040 common=1   ← background job
```

**Fix:** `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`. On a single-slot server
there is no "cheap" sibling to route to; there is only contention.

---

## 3. The disk cache can starve itself

Checkpoints are **cumulative full prefixes** at ~13.5 KiB/token, saved every
~20,480 tokens of prefill. One 320k-token conversation therefore writes a ladder
of ~21 overlapping snapshots totalling **~46 GiB** [measured], and roughly
**52 GiB/hour** of write volume during active use.

At a 64 GiB budget that is self-defeating. The checkpoints written *by* a
re-prefill evicted the checkpoints that would have *prevented* the next one:

```
18:45:12  kv cache evicted reason=disk-cache-full tokens=163840 hits=0
18:46:59  kv cache evicted reason=disk-cache-full tokens=184320 hits=0
...
18:59:39  kv cache evicted reason=disk-cache-full tokens=307200 hits=0
```

Every evicted rung had `hits=0`; the eviction policy is hit-weighted, so
never-yet-used intermediate rungs die first even when they are the ones you are
about to need. Raising the budget to 256 GiB stopped it. Note the cache reached
**225 GB** on disk in normal use — budget accordingly.

---

## 4. Prefix divergence is the actual killer, and caching cannot fix it

Periodically the client rewrote conversation history at a slowly-advancing
boundary, invalidating everything after it:

```
common=111984
common=119559
common=119698
```

Roughly 119.6k into a 402k-token conversation. Each occurrence forced a
re-prefill of ~280k tokens. Observed duty cycle:

```
19:30:22  prefill done 1747s   → 10 useful turns over 6 min
19:38:33  common=119559        → diverged, 30-min re-prefill
20:08:34  prefill done 1791s   →  2 useful turns over 2 min
20:13:58  common=119698        → diverged again
```

**~30 minutes of prefill per 2–10 turns.**

**The important part [derived]:** a *perfect* cache would barely help. At the
16:55 event the prefix diverged at token 111,984 with a 325,568-token prompt.
Resuming from the 102,400 checkpoint meant prefilling 223,168 tokens in 1,213.9s
(183.8 t/s). An idealised cache with a snapshot at every token could resume at
111,984 and would still prefill 213,584 tokens — **~1,162s, a saving of 4%.**

Tokens after a divergence point have *changed*. Their K/V values have never been
computed in that context. No storage tier substitutes for arithmetic that has not
happened. Cache design is not the lever; not diverging is.

---

## 5. Long prefill collides with client timeouts, catastrophically

Prefill grew with the conversation until it crossed the client's first-byte
budget:

| Prefill | Duration | Budget |
|---|---:|---:|
| 19:30 | 1747.5s | 1800s |
| 20:08 | **1791.5s** | 1800s |
| next | >1800s | 1800s → **API error** |

The failure mode is not a lost turn. Each of the 10 retries re-sends the same
prompt and re-prefills for ~30 minutes. One timeout becomes hours of thrash.

Set `CLAUDE_SLOW_FIRST_BYTE_MS` / `CLAUDE_STREAM_IDLE_TIMEOUT_MS` well above
worst-case prefill, and treat a timeout here as a correctness bug, not a hiccup.

---

## 6. Decode at depth is dominated by the KV read, not the weights

Decode reads active weights **plus the entire KV cache**, every token. At long
context the second term dwarfs the first.

**Qwen3-Coder-30B-A3B Q8_0, same session [measured]:**

| Context | Decode |
|---|---:|
| shallow | **64.95 t/s** |
| ~116k | 14.86 t/s |
| ~130k | 13.34 t/s |
| deeper | **11.05 t/s** |

Fitting those two endpoints (15.4 ms/token shallow, 75 ms at 130k) gives
~200 GB/s effective; the shallow point alone (3.3B active × 1.06 B/param ÷
15.4 ms) gives **~227 GB/s** — i.e. decode is memory-bound and already saturating
the bus.

**KV cost per token varies enormously by architecture** [derived from configs]:

| Model | KV/token (f16) | Why |
|---|---:|---|
| DeepSeek V4 Flash | **13.5 KiB** | compressed sparse attention (ratio 4 / 128) |
| gpt-oss-120b | ~36 KiB | 18 of 36 layers sliding-window (128) |
| Qwen3-Coder-30B | 96 KiB | 48 layers, all full attention |
| GLM-4.5-Air | ~184 KiB | 46 layers × 8 KV heads × 128 |
| Qwen3-235B-A22B | ~188 KiB | 94 layers |

At 512k context that is 7 GiB versus 94 GiB. **On a fixed memory budget,
attention architecture decides your maximum context far more than parameter
count does.**

`--cache-type-k/v q8_0` roughly halves it and is the single highest-leverage flag
for long-context decode.

---

## 7. MXFP4 is the only quant with hardware acceleration on GB10

In `ggml/src/ggml-cuda/mmq.cu`:

```c
const bool use_native_fp4 = blackwell_mma_available(cc) &&
    (src0->type == GGML_TYPE_MXFP4 || src0->type == GGML_TYPE_NVFP4);
```

`blackwell_mma_available()` gates on `cc >= BLACKWELL && cc < RUBIN`. GB10 reports
**12.1**, so it qualifies. MXFP4/NVFP4 weights execute on real FP4 tensor cores.
Every other GGUF quant (Q8_0, Q4_K_M, IQ3_XXS …) is a llama.cpp block format with
no hardware equivalent and must be dequantized first.

Bytes per parameter, which is what memory-bound decode actually charges for:

| Format | Bytes/param |
|---|---:|
| fp16 | 2.00 |
| Q8_0 | ~1.06 |
| **MXFP4** | **~0.56** |

Consequence [derived]: gpt-oss-120b (5.1B active, MXFP4) moves **~2.9 GB/token**
while Qwen3-Coder-30B (3.3B active, Q8_0) moves **~3.5 GB/token**. A 116.8B model
is cheaper per token than a 30.5B one. **Format beats parameter count here.**

---

## 8. There is no universal prefill ceiling — `ubatch` and format each move it ~1.3×

**This finding originally claimed a ~8 TFLOP/s hardware ceiling. That was wrong,
and E2/E3 falsified it.** The original observation and its correction are both
kept here, because the error is instructive.

**The original observation.** Two production servers, normalising throughput by
active parameters (`2 × active × t/s`):

| Model | Active | Prefill | Effective |
|---|---:|---:|---:|
| Qwen3-Coder-30B Q8_0 | 3.3B | 1,090 t/s | 7.19 TFLOP/s |
| DeepSeek-V4-Flash IQ3_XXS | 13.0B | 300 t/s | 7.80 TFLOP/s |

Within 8% of each other despite 4× different active-parameter counts. That looked
like a ceiling, and the suspected cause was dequantisation overhead.

**All three models, one harness [measured].** `llama-bench`, `-n 0`, 3
repetitions, `-fa on`:

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

### Why the ceiling was not real

**gpt-oss Q4_K_M reaches 12.35–12.90 TFLOP/s at the same `ub=512`** — a
conventional dequant-path format, well clear of 8. Qwen's 7.19 and V4's 7.80
landing together was a coincidence of two dequant-heavy models both running at
the default ubatch, not a shared hardware limit.

**The harness was not the confound either — it contributes essentially nothing.**
A same-depth, same-ubatch check against live `llama-server`:

```
llama-bench  ub=2048  pp65536       349.63 t/s   (predicted)
production   ub=2048  62,903 tok    349.69 t/s   (observed)
```

Agreement to four significant figures, through the full server path — HTTP,
jinja templating, tokenisation, SSE. **`llama-bench` numbers transfer directly to
production.** The original production figures were sound measurements; only the
interpretation was wrong.

### What actually moves prefill

**1. `ubatch` — free, and the largest single lever** (see #12):

| Model | pp4096 | pp65536 |
|---|---:|---:|
| gpt-oss MXFP4 | +29.5% | +18.7% |
| **V4 IQ3_XXS** | **+41.3%** | **+31.0%** |

V4 gains most, and V4 is what runs in production at the default 512.

**2. Format — controlled, and real** (see #13). MXFP4 vs Q4_K_M, identical
weights, architecture, harness and active-parameter count: **1.19–1.43×**.

**3. Architecture — uncontrolled.** V4 sits ~40% below gpt-oss Q4_K_M even after
normalising for active parameters. Plausible causes: 284B total parameters means
far heavier MoE expert-gather traffic; the compressed-attention indexer adds work
the active-parameter count does not capture; IQ3_XXS uses lookup-table
dequantisation, costlier than Q4_K_M's. Not separated by these experiments.

### Caveat on the metric

"Effective TFLOP/s" is `2 × active_params × t/s` — a **[derived] proxy**, not a
measured FLOP count. It is sound for comparing one model against itself across
formats or ubatch sizes. Across architectures it silently assumes the
active-parameter figure captures all the work, which for V4's indexer and heavy
expert gather it does not. **Cross-model rows in that table are indicative;
same-model rows are evidence.**

---

## 9. gpt-oss-120b cannot be stretched past 131k

Upstream config:

```json
"rope_scaling": {"rope_type":"yarn","factor":32.0,
                 "original_max_position_embeddings":4096}
```

4096 × 32 = 131,072. Its window is *already* the YaRN-extended one; asking for
more stacks a second YaRN on the first.

**Two traps.** llama.cpp caps `n_ctx_slot` back to `n_ctx_train` but **still
applies the rope flags you passed**, silently corrupting positional encoding —
the server looks fine and the model quietly gets worse. And `--cache-reuse` is
disabled automatically under sliding-window attention (logged, easy to miss).

### What this does and does not establish

The generalisable rule [measured]: **run at the vendor's declared
`max_position_embeddings` and never pass rope flags yourself.** Stacking your own
scaling on top of the vendor's yields no extra context *and* corrupted positions.

It says nothing about whether factor 32 is itself too aggressive. gpt-oss was
rejected here for its **context ceiling**, not its quality — its output was never
evaluated, because the rope flags were live on the only instance that ran. Factor
32 is OpenAI's own shipped, trained and validated configuration.

**On rope scaling generally.** The ivory-tower ideal is a model trained natively
at the target length: RoPE has a fixed angular budget, and YaRN packs more
positions into a budget sized for fewer. Training on the stretched ruler teaches
the model to read it, but where two positions land on nearly identical angles, no
amount of training separates them — the information is not in the encoding. YaRN
is deliberate about where it spends that loss (`beta_fast`/`beta_slow` ramp
between leaving high-frequency dims — local ordering — nearly untouched and
compressing the low-frequency, long-range ones).

Native training at 1M does not exist, and not by oversight: attention is O(n²),
and there are not enough genuine million-token documents to train on. Every
long-context model is extended in stages; "native" is a spectrum, not a binary.
V4 Flash's own 65,536 base is almost certainly not its from-scratch length
either.

**[hypothesis]** The comparable numbers for model selection are therefore *base
length* and *stretch factor*, not the presence of scaling:

| Model | Base | Factor | Result |
|---|---:|---:|---|
| DeepSeek V4 Flash | 65,536 | ×16 | 1M |
| gpt-oss-120b | 4,096 | ×32 | 131k |

V4 Flash is stretched less aggressively from a base 16× longer. Whether that
translates into measurably better long-context fidelity is **untested** — see
E5.

---

## 10. llama.cpp beats the purpose-built engine for DeepSeek V4

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

Better quant, double the context, faster decode, prefill a wash. Prefill parity
is itself notable: a hand-tuned single-model engine and llama.cpp's generic CUDA
path land in the same place — consistent with #8, where neither is the binding
constraint.

**Verified [measured]:** `n_ctx_slot = 1048576`, no capping; 106 of 121 GB
resident under `mlock`; `/v1/messages` returns native `thinking` blocks; a
generated SWAR `popcount64` compiled clean under `-Wall -Wextra` and matched
`__builtin_popcountll` on all test cases.

### Throughput vs depth — DeepSeek-V4-Flash UD-IQ3_XXS, 1M ctx, q8_0 KV

| Prompt depth | Prefill | Decode |
|---:|---:|---:|
| ~0 (43 tok) | — | **16.30 t/s** |
| 16k (in-flight) | 297 t/s | — |
| 61k (in-flight) | 250 t/s | — |
| **116k (complete)** | **210.5 t/s** | **12.44 t/s** |

Both curves decay with depth for the same reason: prefill attention is
superlinear in context, and decode must re-read a KV cache that grows every
token (#6). A real 116k-token session costs **~9 minutes of one-time cold
prefill**, after which incremental turns are seconds — provided the prefix does
not diverge (#4).

Note the caveat on the shallow decode figure: 276 of 517 tokens in that smoke
test were `thinking` blocks. V4 Flash is a reasoning model, so a substantial and
variable fraction of every response is deliberation the user never sees.

---

## 11. Prefix caching assumes append-only growth; coding agents are not append-only

Two different things get called "the KV cache", and only one of them is a
questionable fit here.

**Within a generation**, the KV cache is load-bearing and not optional. Without
it, producing token N re-derives K/V for all N−1 predecessors on every step; at
116k context that turns an ~80 ms token into a full ~9-minute prefill.

**Across requests**, prefix caching is a different bet, and it bets on
*append-only* growth — the ChatGPT shape, where a thread starts small and only
ever grows at the end. A coding agent is not that shape. It front-loads a large
context to reach a reasoning result, then rewrites that context wholesale at
structurally meaningful moments: plan mode → execution, subagent spawn and
return, compaction, tool-result trimming.

The payoff is therefore **bimodal, not average** [measured]:

```
19:30:22  prefill done 1747s
19:30:59  prompt done 0.579s
19:31:19  prompt done 4.977s
...  ten turns, all 1–5s, at 395k tokens
19:38:33  common=119559  ← divergence, everything after is discarded
```

Ten cached turns cost ~9.5 minutes total; uncached they would have cost ~90
[derived]. So prefix caching is worth roughly **9× while the prefix holds, and
exactly nothing across a break.** Whether it "makes sense" depends entirely on
divergence frequency, which is a property of the *client*, not the server.

**The mitigation exists and is named.** Much of what a divergence discards is not
changed content — it is identical content at shifted positions (compaction drops
tokens; it does not rewrite what follows). llama.cpp's `--cache-reuse N` targets
precisely this, re-applying rope to relocate cached K/V:

```
--cache-reuse N   min chunk size to attempt reusing from the cache via KV shifting
```

**It is unavailable on DeepSeek V4** — `src/llama-kv-cache-dsv4.cpp`:

```c
bool llama_kv_cache_dsv4::get_can_shift() const {
    // Compressed row metadata uses block-derived positions. Keep shifting
    // disabled until DSV4 compressed-cache shift semantics are wired.
    return false;
}
```

`llama_memory_can_shift()` returning false silently disables both `ctx_shift`
and `n_cache_reuse` in the server.

**The tension worth naming:** V4's compressed rows are simultaneously why 512k of
KV fits in 7 GiB (#6) *and* why positions are block-derived and cannot be
shifted. **The architectural feature that buys the context is the feature that
blocks the cache repair.** The two properties are the same property.

The comment reads as unimplemented rather than impossible, so wiring DSV4
compressed-cache shift semantics is an available upstream contribution — and it
would directly address the stalls in #4.

**Honest limit:** shifting recovers *position* changes only. If the client
rewrites content rather than relocating it, no shifting helps. Which makes #4
(what actually changes at ~119.6k) the question that decides whether any of this
is worth building.

---

## 12. `--ubatch-size 2048` buys 19–30% of prefill, free

`n_ubatch` defaults to 512, which caps arithmetic intensity: each micro-batch
re-reads weights that could have been amortised over more tokens. Raising it is a
single flag.

**Clean comparison [measured]** — same model, same harness, same run, one
variable (gpt-oss-120b MXFP4, `llama-bench`, 3 repetitions):

| Prompt depth | `-ub 512` | `-ub 2048` | Gain |
|---|---:|---:|---:|
| 4,096 | 1800.6 t/s | 2332.0 t/s | **+29.5%** |
| 16,384 | 1732.2 t/s | 2186.6 t/s | **+26.2%** |
| 65,536 | 1310.4 t/s | 1555.3 t/s | **+18.7%** |

No confound: identical weights, identical harness, only `-ub` differs. The gain
shrinks with depth as attention takes a larger share of the work.

**Confirmed in production [measured].** Applied to the live 1M-context V4 server
and sent a 62,903-token prompt:

```
llama-bench  ub=2048  pp65536       349.63 t/s   (predicted)
production   ub=2048  62,903 tok    349.69 t/s   (observed)
```

Against the `ub=512` bench at the same depth (266.94 t/s) that is **+31.0%** —
matching the predicted +31.0% exactly. The benchmark transfers with no
server-path penalty.

**Cost: ~6 GB of compute buffer.** At 1M context the V4 server went from 106 GB
resident (`ub=512`) to **112 of 121 GB**, leaving ~8 GB headroom instead of ~14.
It loads and runs, but the margin is thin — `DS_UBATCH=512` reverts if a future
config OOMs on load.

---

## 13. Native FP4 is worth 1.19–1.43× on prefill — controlled

**The controlled experiment.** One model (gpt-oss-120b), one harness
(`llama-bench`), one architecture, 5.1B active either way. The MXFP4 file was
requantised in place to Q4_K_M (4.8 bpw, dequant path) so that **format is the
only variable**:

| Test | ub | MXFP4 | Q4_K_M | Ratio |
|---|---:|---:|---:|---:|
| pp4096 | 2048 | 2332 t/s | 1786 t/s | **1.31×** |
| pp16384 | 2048 | 2187 t/s | 1704 t/s | 1.28× |
| pp65536 | 2048 | 1555 t/s | 1307 t/s | 1.19× |
| pp4096 | 512 | 1801 t/s | 1265 t/s | **1.43×** |
| pp16384 | 512 | 1732 t/s | 1211 t/s | 1.43× |
| pp65536 | 512 | 1310 t/s | 985 t/s | 1.33× |

**The native FP4 tensor-core path (#7) is worth a consistent 19–43% on prefill.**
The advantage is largest at small ubatch and shallow depth — i.e. where
matrix-multiply dominates and attention does not — which is what a
dequantisation-avoidance explanation predicts.

Note the control is *heavier*: Q4_K_M came out 81.82 GiB against MXFP4's 59.03
(the Q4_K_M mapping promotes some expert tensors to q5_0). More bytes should make
it slower, so this biases against MXFP4 rather than flattering it — but prefill
here is not bandwidth-bound (#8), so the effect should be small either way.

### What this means for a custom quant

| Lever | Prefill gain | Cost |
|---|---:|---|
| `-ub 2048` | +19–41% | **one flag** |
| MXFP4 format | +19–43% | 144 GiB download, imatrix (days), requantise, eval |

They stack — MXFP4 at ub2048 is **1.84×** over Q4_K_M at ub512 — but the free
flag delivers roughly what the custom quant does. The marginal return on weeks of
work is ~30%, not the 3× that appeared to justify the project before the control
was run.

**Additional blocker for V4 specifically:** a pure MXFP4 build of V4 Flash is
144.3 GiB and does not fit in 121 GB. Capturing this gain would mean a hybrid —
MXFP4 on the layers that fit, IQ2/IQ3 elsewhere — so only a fraction of the
matmul work would take the native path, proportionally reducing the 1.19–1.43×.

---

## 14. Output tokens cost ~16–30× more than input tokens here

A direct consequence of the batching asymmetry in the header. Per token
[derived from measured throughput]:

| | Rate | Relative cost |
|---|---:|---:|
| Reading input (prefill) | 194.9 t/s *(production, `ub=512`)* | 1× |
| Reading input (prefill) | 473 t/s *(`ub=2048`, shallow)* | 1× |
| Writing output (decode) | 12.45 t/s | **~16× / ~38×** |

One generated token costs what 16 input tokens cost on the production config,
and ~38 once `-ub 2048` speeds up reading without touching writing (#12).
Improving prefill *widens* this gap.

**Why it matters more than it looks.** V4 Flash is a reasoning model: in a smoke
test, **276 of 517 output tokens were `thinking` blocks** — roughly half of all
decode time spent on deliberation the user never sees.

This inverts a habit carried over from hosted models, where input is the thing
you economise. Here, what the model *says* is the expensive part:

- Terser system prompts help twice — less to read, and less to imitate
- Lower reasoning effort where a task does not need deliberation
- Asking for code rather than code-plus-explanation

**Keep the magnitude honest.** Decode was 11.1 of 84.5 minutes in the case study.
Halving thinking output saves ~5 minutes. Redundant prefill is 57.9 minutes
(E1). This is a real lever and a small one.

---

## 15. E1 ANSWERED — a trailing system message rewrites the *head* of the prompt

The single largest cost in this whole document (#4, #11, and 68.6% of measured
model time in the case study) has one cause, and it is not what the earlier
findings guessed.

**Claude Code appends ephemeral `system`-role messages to the END of the
`messages` array.** DeepSeek V4's chat template **hoists every system message to
the TOP** of the rendered prompt:

```
line 27, 34:  loops that COLLECT system messages into ns.system_prompt
line 66:      {{- ns.system_prompt -}}      <- emitted near the top
line 70, 76:  loops that render the actual conversation turns
```

So appending one short system message at index 32 of 33 changes the rendered
prompt roughly **9,200 tokens in — about 6% of the way through** — instead of at
the end where it was written. A tail append becomes a near-head insertion.

**It is an insertion, not a rewrite [measured].** Reconstructing the system block
from the dumps shows it is strictly append-only:

```
#7 -> #8:  36,901 -> 37,404 chars, common prefix 36,901 (all of #7's block)
#8 -> #9:  37,404 -> 38,280 chars, common prefix 37,404 (all of #8's block)
```

Everything after the insertion is byte-identical, merely shifted by ~125 tokens.

**Perfect correlation over 9 captured requests [measured]:**

| req | msgs | last role | system indices | server |
|---:|---:|---|---|---|
| #2 | 21 | user | 1, 8, 15, 18 | reused |
| **#3** | 22 | **system** | 1, 8, 15, 18, **21** | **FULL RE-READ** |
| #4 | 24 | user | 1, 8, 15, 18, 21 | reused |
| #5 | 26 | user | … | reused |
| #6 | 28 | user | … | reused |
| #7 | 30 | user | … | reused |
| **#8** | 33 | **system** | …, **32** | **FULL RE-READ** |
| **#9** | 36 | **system** | …, **35** | **FULL RE-READ** |

Every request ending in a system message re-read everything; every request
ending in a user message reused the cache. No exceptions.

The worst observed instance: **task 14355 re-read 149,679 tokens — nine and a
half minutes — to accommodate 257 new tokens.**

### Why the earlier analysis missed it

Message-level hashing said these prompts were 89–99% identical, and they *are* —
in JSON. The divergence only exists after template rendering, where a tail
element is relocated to the head. **Any cache analysis done on the client's
request body will mispredict; the rendered prompt is the only thing that
matters.**

### Consequences

**E6 is dead — but not for the reason first assumed.** The content *is* shifted,
so shifting sounds like the right remedy. It is not, because a sliding-window
model cannot resume mid-sequence at all. `tools/server/server-context.cpp`:

```c
"forcing full prompt re-processing due to lack of cache data
 (likely due to SWA or hybrid/recurrent memory)"
pos_next = 0;  n_past = 0;
```

Reuse is gated on `pos_min >= pos_min_thold`, where the threshold is derived
from `n_swa`. V4 keeps a 128-token raw sliding window, so the sliding layers
retain KV only for the most recent 128 positions — there is no stored state at
position 9,200 to shift. **The server does not partially reuse and then fail; it
detects the impossibility up front and resets to zero.** That is why the measured
reuse was 0 rather than the ~9,200 tokens the common prefix would suggest.

Same irony as #11, one level deeper: the sliding window that makes 1M context
affordable is exactly what makes mid-prompt recovery impossible. Weeks of C++
work avoided by one afternoon of measurement.

**Corollary: only append-only prompts can be cached on this model.** Any mutation
anywhere but the very end costs a full re-read, regardless of how small it is or
whether the content afterwards is preserved. Padding or reserving space does not
help — each token's cached state is derived from every token before it, so
changing content at position N invalidates everything after N even if the length
is unchanged.

**The fix is a jinja edit, not a kernel.** `llama-server --chat-template` accepts
an override. Rendering system messages that appear *after* the first user message
in place — rather than hoisting them — makes them append-only and preserves the
prefix.

**Caveat:** that is a behaviour change, not a pure optimisation. A system-reminder
rendered inline mid-conversation may be weighted differently by the model than
one hoisted into the system block. Needs an A/B on output quality, not just on
throughput.

### Generality

This is not Spark-specific and not DeepSeek-specific. **Any client that appends
system messages mid-conversation, against any template that hoists system
messages, destroys prefix caching on every such request.** The combination is
silent: both components are behaving as designed.

---

## Case study: one real agentic session

A `/pr-check` skill run against a real open PR on a TypeScript compiler project
(`jlaustill/c-next` #1140). DeepSeek-V4-Flash UD-IQ3_XXS, 1M ctx, q8_0 KV, driven
by Claude Code over `/v1/messages`. Not a synthetic benchmark — an actual task
the author needed done.

### Where the time went [measured]

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

`necessary` is [derived] — estimated as the largest single prefill plus the sum
of all incrementals, i.e. a lower bound on unavoidable reading. Session context
was ~146k tokens, so 858k of prefill means the conversation was re-read roughly
six times over.

**This reproduces #4 on llama.cpp.** Prefix divergence is a client-side
behaviour, not an artifact of `ds4-server`.

### The number that reframes everything

**68.6% of this machine's working life was spent re-reading context it had
already read.**

Decode — the thing quantisation choice, KV cache type and active-parameter count
mostly govern — accounted for 13%. It is close to a rounding error on this
workload.

That split separates two kinds of optimisation which are easy to conflate:

- **Faster prefill** — MXFP4 tensor cores (#7), larger `ubatch`, quantisation
  format. These scale *all* 73.4 minutes and are real wins.
- **Less prefill** — fixing or absorbing divergence. Only this touches the 57.9
  minutes of waste, and no format or quantisation change affects it at all.

The two multiply rather than compete. Wiring
`llama_kv_cache_dsv4::get_can_shift()` addresses the larger share — **if** the
divergence relocates tokens rather than rewriting them (E1).

**Numbers frozen at end of session (2026-08-09).** Final totals, not a snapshot.

### Quality [measured, with caveats]

The model produced a correct and well-structured report: identified the failing
build with the specific TypeScript errors, recognised the patch was a no-op,
located two root causes in two different subsystems (state lifetime in
`convertToHeaderSymbols()`; a mangled-vs-bare-name mismatch in
`resolveTargetParam`'s SymbolTable lookup), flagged the missing regression test
against project convention, and declined to start coding without confirmation.

**Caveat for scoring:** the report cites "the automated review" as the source of
the four issues, so the root-cause analysis was partly *summarised* rather than
*derived*. What is unambiguously the model's own work: it ran the reproduction
and confirmed the bug still occurs on the branch ("verified empirically"), it
recognised the fix spans unrelated subsystems, and it recommended a
regression-test-first order of work.

This is a meaningful improvement over Qwen3-Coder-30B-A3B (3.3B active), which
produced a confidently wrong, non-compiling patch on the same repository. **13B
active appears to clear a bar that 3.3B does not** — on analysis. Whether it can
*write* the fix is untested, and is the harder task; PR #1140 exists precisely
because something already produced a plausible-looking wrong patch.

---

## Practical gotchas

- **`sudo` scripts fail silently** when launched through a non-interactive
  wrapper — the password prompt has no TTY. Run them in a real terminal.
- **`grep` needs `--line-buffered`** when following a log, or a low-volume stream
  looks dead for minutes.
- **`--load-mode mlock` needs `LimitMEMLOCK=infinity`** in the systemd unit.
- **"DSpark" is taken** — it is DeepSeek's own speculative draft head
  (`markov_head`, `confidence_head`), not anything to do with DGX Spark. Do not
  name a Spark quant `ds4-spark`.

## Partially answered

**Is ~3 bpw enough for real agentic coding?** V4 Flash (13B active) produced a
sound PR analysis on a real issue where Qwen3-Coder-30B-A3B (3.3B active)
produced a confidently wrong, non-compiling patch on the same repository (see
case study). **13B active clears a bar that 3.3B does not — on analysis.**
Whether it can *write* a correct fix is E4, and is the harder half.

Everything else open is tracked as E1–E6 at the top of this document.

## Reproduction

Scripts live in `/home/linux`: `build-llamacpp.sh`, `dsv4-server.sh`,
`qwen-server.sh`, `gptoss-server.sh`, `install-*.sh`, `cleanup-models.sh`.
