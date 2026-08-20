# Findings

What is true, as measured on one machine. Original findings 2026-08-08/10.
Falsification pass 2026-08-12/18.

One claim per file. **The directory is the status.** A file moves between
directories when its status changes, and its `id` stays the same.

| directory | meaning |
|---|---|
| `verified/` | Survived a deliberate attempt to falsify it |
| `unverified/` | Measured once, not yet re-tested against a falsification attempt |
| `refuted/` | Tested and found false |

There is no `corrected/`. A correction is a fact about a claim's history, not a
status of the claim. Where a measurement replaced an earlier figure, the file
carries a `supersedes:` field naming what it replaced. Where a whole
recommendation turned out to be false, the false version lives in `refuted/` and
names what replaced it.

`refuted/` is not an attic. Each file there records a claim that is still
reachable by plausible reasoning, and that costs real time if you act on it.

## The one sentence the rest of this follows from

A DGX Spark buys capacity at the price of bandwidth. Its 121 GB of unified
LPDDR5X holds a 284B-parameter model with a million tokens of context, which no
consumer GPU can touch. It moves bytes at roughly a quarter the speed of a
dedicated card. See [00](verified/00-capacity-for-bandwidth.md).

## Terminology

| Term | What the model is doing | llama.cpp log label | Bound by |
|---|---|---|---|
| **Prefill** | *Reading* input tokens, building KV | `prompt eval time` | compute — parallel across tokens |
| **Decode** | *Writing* output tokens, one at a time | `eval time` | memory bandwidth — serial |

Naming trap: bare **`eval time` is decode**. `prompt eval time` is prefill. The
two sit adjacent in the log and are easy to swap. `llama-bench` calls them `tg`
and `pp` respectively.

| Term | Meaning |
|---|---|
| **Necessary prefill** | The irreducible minimum. One pass over the context, plus the genuinely new tokens each turn adds |
| **Redundant prefill** | Re-reading tokens already processed, because cache invalidation threw the work away |

Redundant prefill is invisible in any single request. Every prefill looks
legitimate on its own. It appears only when you sum a whole session.

## Start here

The largest cost measured on this box, and its fix:
[15a](verified/15a-a-trailing-system-message-rewrites-the-head.md) →
[15b](verified/15b-inline-rendering-removes-96-percent-of-redundant-prefill.md) →
[15c](verified/15c-the-patched-template-solves-10-of-10.md).

Where the time actually went:
[17](verified/17-case-study-84-5-minutes-of-model-time.md).

Methodology, the full test log and every falsified assumption live in
[../NOTES.md](../NOTES.md). This tree holds only the conclusions.

## Index

Regenerate this block with `tools/findings-index.py`. Validate the tree without
writing with `tools/findings-index.py --check`.

<!-- BEGIN INDEX -->

### verified (33)

Survived a deliberate attempt to falsify it.

- **[00](verified/00-capacity-for-bandwidth.md)** — A DGX Spark buys memory capacity and pays with memory bandwidth
- **[01a](verified/01a-cold-max-tokens-default-disables-disk-cache.md)** — A default of 30000 silently disables the disk KV cache
- **[01b](verified/01b-disk-kv-cache-is-worth-9-6x-on-a-cold-start.md)** — The disk KV cache is worth 9.6x on a cold start
  - supersedes: The original claim of 1517.4s to 1.4s, described as roughly 1000x.
- **[02a](verified/02a-small-fast-model-alias-shares-one-slot.md)** — Both model ids resolve to one model on one server slot
- **[03](verified/03-the-disk-cache-can-starve-itself.md)** — The disk cache can evict the checkpoints that would have helped it
  - supersedes: A correction issued during verification, which read the configured step from source and concluded the spacing was 10,240. That correction was itself wrong and is retracted.
- **[04a](verified/04a-prefix-divergence-defeats-caching.md)** — Prefix divergence is the real cost, and no cache design fixes it
- **[05a](verified/05a-the-client-first-byte-budget-is-301-seconds.md)** — The client first-byte budget is about 301 seconds and cannot be raised
  - supersedes: The original claim that the budget defaults to 1800 s.
- **[06a](verified/06a-shallow-decode-is-bandwidth-bound.md)** — Shallow decode is bandwidth-bound on weights
- **[06c](verified/06c-kv-cost-per-token-by-architecture.md)** — Attention architecture decides maximum context far more than parameter count
- **[07a](verified/07a-the-native-fp4-path-is-prefill-only.md)** — MXFP4 has hardware acceleration on GB10 for prefill only
  - supersedes: The original claim, which did not bound the acceleration to prefill and implied it applied to decode as well.
- **[08a](verified/08a-there-is-no-universal-prefill-ceiling.md)** — There is no universal prefill ceiling
- **[08b](verified/08b-the-bench-noise-floor-is-4-percent.md)** — The llama-bench harness transfers to production, but its precision does not
  - supersedes: The original claim that llama-bench agreed with production to four significant figures, at 349.63 predicted against 349.69 observed. That agreement was coincidence.
- **[09a](verified/09a-rope-flags-are-silently-applied.md)** — The server caps context but does not reset the rope parameters
- **[09b](verified/09b-rope-mismatch-costs-34x-perplexity.md)** — A stacked rope flag degrades perplexity by 34x, and only at full context
- **[09c](verified/09c-damage-tracks-mismatch-not-stretch-factor.md)** — Rope damage tracks mismatch with the trained mapping, not the stretch factor
- **[10b](verified/10b-ds4-server-prefills-faster-than-llamacpp.md)** — ds4-server prefills faster than llama.cpp on the same conversation
- **[10c](verified/10c-llamacpp-can-quantize-the-v4-kv-cache.md)** — llama.cpp can quantize the V4 KV cache, and that is what makes 1M context fit
- **[11a](verified/11a-prefix-cache-payoff-is-bimodal.md)** — Prefix caching assumes append-only growth, and coding agents are not append-only
- **[11b](verified/11b-cache-reuse-is-unavailable-on-v4.md)** — --cache-reuse is unavailable on DeepSeek V4
- **[12a](verified/12a-ubatch-2048-buys-19-to-31-percent-of-prefill.md)** — --ubatch-size 2048 buys 19 to 31 percent of prefill
  - supersedes: The original heading, which claimed 2048 is the optimum. Nothing measured supports optimality. See Limits.
- **[13a](verified/13a-mxfp4-beats-q4-k-m-on-prefill.md)** — MXFP4 beats Q4_K_M on prefill by 1.19x to 1.47x
- **[13b](verified/13b-the-native-path-is-worth-1-16x-to-1-34x.md)** — The native FP4 path is worth 1.16x to 1.34x, and fewer bytes are worth 1.04x to 1.11x
  - supersedes: The original attribution of the full 1.19x-1.43x to the hardware path. That range is the combined effect of the path and the smaller file.
- **[13c](verified/13c-the-native-fp4-path-costs-6-4-percent-perplexity.md)** — The native FP4 path costs 6.4 percent perplexity
  - supersedes: The original treatment of the native FP4 path as a pure win. The accuracy side was never measured.
- **[13d](verified/13d-the-custom-hybrid-quant-is-not-worth-building.md)** — A custom hybrid MXFP4 quant for V4 is not worth building
- **[14](verified/14-output-tokens-cost-17x-input-tokens.md)** — Output tokens cost about 17x more than input tokens
  - supersedes: The original figure of ~38x, which divided shallow prefill (473 t/s) by deep decode (12.45 t/s). Those are different depths and the ratio is not meaningful. The claim that improving prefill widens the gap rested on the 38x figure and is dropped.
- **[15a](verified/15a-a-trailing-system-message-rewrites-the-head.md)** — A trailing system message rewrites the head of the prompt
- **[15b](verified/15b-inline-rendering-removes-96-percent-of-redundant-prefill.md)** — In-place system-message rendering removes 96.4 percent of redundant prefill
- **[15c](verified/15c-the-patched-template-solves-10-of-10.md)** — The patched template solves 10 of 10 eval tasks against stock's 4 of 10
- **[15d](verified/15d-the-v4-template-is-the-outlier.md)** — V4's template is the outlier, and in-place rendering is the mainstream convention
- **[15e](verified/15e-gpt-oss-drops-mid-conversation-system-messages.md)** — gpt-oss silently drops mid-conversation system messages
- **[16](verified/16-a-hardcoded-return-zero-costs-29000-tokens.md)** — One hardcoded return 0 costs about 29,000 tokens per session
- **[17](verified/17-case-study-84-5-minutes-of-model-time.md)** — One real agentic session spent 68.6 percent of model time re-reading context
- **[18](verified/18-operational-gotchas.md)** — Six operational traps that fail silently

### unverified (5)

Measured once. Not yet re-tested against a falsification attempt. Each file names the test that would close it.

- **[02b](unverified/02b-background-traffic-evicts-the-agent-cache.md)** — Background traffic evicts the agent's cache
- **[04b](unverified/04b-the-29-7-percent-divergence-event.md)** — The 29.7 percent divergence event is unexplained
- **[05b](unverified/05b-what-governs-the-production-timeout.md)** — An idle timeout, not the first-byte budget, governs production
- **[10a](unverified/10a-llamacpp-beats-ds4-server-for-v4.md)** — llama.cpp beats ds4-server for DeepSeek V4
- **[12b](unverified/12b-the-ubatch-2048-memory-margin.md)** — The ubatch 2048 memory margin survives a worst-case request

### refuted (4)

Tested and found false. Kept because each one is still reachable by plausible reasoning, and because acting on it costs real time.

- **[05c](refuted/05c-slow-first-byte-ms-fixes-prefill-timeouts.md)** — REFUTED: CLAUDE_SLOW_FIRST_BYTE_MS fixes prefill timeouts
  - replaced by: 05a, 05b
- **[06b](refuted/06b-q8-0-kv-speeds-up-long-context-decode.md)** — REFUTED: q8_0 KV cache speeds up long-context decode
  - replaced by: 06a, 06c
- **[07b](refuted/07b-mxfp4-outdecodes-q8-0.md)** — REFUTED: MXFP4's fewer bytes make it decode faster than Q8_0
  - replaced by: 07a
- **[16b](refuted/16b-cache-reset-is-caused-by-a-small-sliding-window.md)** — REFUTED: the cache reset is caused by a 128-token sliding window
  - replaced by: 16

<!-- END INDEX -->

## Experiments

Every experiment the original document opened is now closed.

| # | Question | Answer |
|---|---|---|
| E1 | What rewrites history mid-conversation? | [15a](verified/15a-a-trailing-system-message-rewrites-the-head.md) |
| E2 | Does a larger `--ubatch-size` help prefill? | [12a](verified/12a-ubatch-2048-buys-19-to-31-percent-of-prefill.md) |
| E3 | Does the native FP4 path beat a dequant format? | [13a](verified/13a-mxfp4-beats-q4-k-m-on-prefill.md), [13b](verified/13b-the-native-path-is-worth-1-16x-to-1-34x.md), [13c](verified/13c-the-native-fp4-path-costs-6-4-percent-perplexity.md) |
| E4 | Can V4 Flash *write* a fix, not just analyse one? | Yes, 10/10 — [15c](verified/15c-the-patched-template-solves-10-of-10.md) |
| E5 | Where is the rope-stretch tolerance threshold? | There is none in the stretch factor — [09c](verified/09c-damage-tracks-mismatch-not-stretch-factor.md) |
| E6 | DSV4 compressed-cache shifting | Dropped. The real reason is [16](verified/16-a-hardcoded-return-zero-costs-29000-tokens.md), and the reasoning that queued it is [16b](refuted/16b-cache-reset-is-caused-by-a-small-sliding-window.md) |
| E7 | Does in-place system-message rendering fix the invalidation? | Yes — [15b](verified/15b-inline-rendering-removes-96-percent-of-redundant-prefill.md) |

## Reproduction

The verification harness, per-test results and raw logs live in `../tools/`,
`../results/` and `../data/`. Server and build scripts live in `/home/linux`.

⚠️ `build-llamacpp.sh` runs `git pull --ff-only`. Every number in this tree is on
llama.cpp commit `687e778`. Running that script moves the checkout and
invalidates comparability.
