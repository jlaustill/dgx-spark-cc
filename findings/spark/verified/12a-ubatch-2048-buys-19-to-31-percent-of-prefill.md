---
id: "12a"
status: verified
title: --ubatch-size 2048 buys 19 to 31 percent of prefill
measured: 2026-08-12
supersedes: "The original heading, which claimed 2048 is the optimum. Nothing measured supports optimality. See Limits."
see_also: ["08a", "12b", "13d"]
---

# --ubatch-size 2048 buys 19 to 31 percent of prefill

**Claim.** `n_ubatch` defaults to 512, which caps arithmetic intensity. Each
micro-batch re-reads weights that a larger batch could have amortised over more
tokens. Raising it to 2048 buys 19% to 31% of prefill for one flag.

## Evidence

Same model, same harness, one variable. gpt-oss-120b MXFP4, three repetitions:

| Prompt depth | published gain | re-measured 2026-08-12 |
|---|---:|---:|
| 4,096 | +29.5% | **+25.8%** |
| 16,384 | +26.2% | **+30.0%** |
| 65,536 | +18.7% | **+18.7%** |

**Confirmed in production.** Applied to the live 1M-context V4 server, a
62,903-token prompt ran at 349.69 t/s against 266.94 t/s at `ub=512`. That is
**+31.0%**.

The `ub=2048` session averaged **275.5 t/s** across a whole agentic session,
against the case study's 194.9 t/s at `ub=512`.

## Limits

**2048 is the largest value tried. It is not a demonstrated optimum.** The
original heading claimed optimality and no measurement supports that claim. Larger
values were not tested.

The flag costs about 6 GB of compute buffer, and that cost is not fully
characterised. See
[12b](../unverified/12b-the-ubatch-2048-memory-margin.md).

This is the largest of the three levers that move prefill speed. See
[08a](08a-there-is-no-universal-prefill-ceiling.md). It does not touch redundant
prefill, which is a larger cost. See
[17](17-case-study-84-5-minutes-of-model-time.md).
