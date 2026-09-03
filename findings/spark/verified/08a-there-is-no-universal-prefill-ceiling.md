---
id: "08a"
status: verified
title: There is no universal prefill ceiling
measured: 2026-08-12
see_also: ["08b", "12a", "13a"]
---

# There is no universal prefill ceiling

**Claim.** Prefill has no fixed hardware ceiling on this box. Ubatch size and
weight format each move it by about 1.3x.

## Evidence

All three models, one harness. `llama-bench`, `-n 0`, three repetitions,
`-fa on`:

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

All twelve rows reproduce on a re-measurement on the same commit. MXFP4 falls
within 4%. Q4_K_M falls within 1% to 7%.

gpt-oss Q4_K_M reaches 12.35 to 12.90 TFLOP/s at `ub=512`. That is a
conventional dequant format, and it sits well clear of the 8 TFLOP/s that once
looked like a hardware ceiling. Two dequant-heavy models simply landed near each
other at the default ubatch size.

## What actually moves prefill

1. **`ubatch`.** Free, and the largest single lever. See
   [12a](12a-ubatch-2048-buys-19-to-31-percent-of-prefill.md).
2. **Format.** Controlled and real, at 1.19x to 1.43x. See
   [13a](13a-mxfp4-beats-q4-k-m-on-prefill.md).
3. **Architecture.** Uncontrolled. V4 sits about 40% below gpt-oss Q4_K_M even
   after normalising for active parameters.

## Limits

The architecture term is not separated by these experiments, and this finding
does not claim to separate it. Three causes are plausible. V4 has 284B total
parameters, which means far heavier MoE expert-gather traffic. Its
compressed-attention indexer adds work that the active-parameter count does not
capture. IQ3_XXS uses lookup-table dequantisation.

"Effective TFLOP/s" is `2 x active_params x t/s`. It is a **derived proxy** and
not a measured FLOP count. It is sound for comparing one model against itself
across formats or ubatch sizes. Across architectures it assumes that the
active-parameter figure captures all the work, which for V4's indexer and heavy
expert gather it does not. **Treat cross-model rows as indicative and same-model
rows as evidence.**
