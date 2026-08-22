---
id: "08b"
status: verified
title: The llama-bench harness transfers to production, but its precision does not
measured: 2026-08-12
supersedes: "The original claim that llama-bench agreed with production to four significant figures, at 349.63 predicted against 349.69 observed. That agreement was coincidence."
see_also: ["08a"]
---

# The llama-bench harness transfers to production, but its precision does not

**Claim.** `llama-bench` predicts production prefill within a few percent, and it
runs slightly optimistic. Its own reported error bars understate the real noise
floor by 4x to 6x.

## Evidence that the claim transfers

Same model, same settings, at 262k ctx, `ub 2048`, q8_0 KV:

| | t/s |
|---|---:|
| `llama-bench` pp131072 | **271.49 +/- 0.27** |
| production, 138,595 tok | 263.0 |
| production, 142,981 tok | 259.2 |
| production, 149,679 tok | 253.5 |
| production, 150,072 tok | 253.2 |

At the closest comparable depth the gap is **3.2%**, with production slightly
slower. That is the expected direction, because production runs deeper and also
pays real HTTP, jinja templating and tokenisation.

Every production point sits 3% to 7% under the bench figure, and the gap
increases monotonically with depth. `llama-bench pp65536 = 350.31` also
reproduces the published 350 t/s almost exactly.

## Evidence that the precision does not transfer

The same `pp4096 ub512` row across four independent process launches spans
**4.3%**, at 1795.72, 1800.58, 1859.99 and 1872.78 t/s.

`llama-bench` reports a within-run sigma of 0.1% to 0.7%. **The harness therefore
understates its own variance by 4x to 6x.**

The originally published four-significant-figure agreement is about 200x tighter
than the instrument can resolve. It was also measured at different depths, at
65,536 against 62,903. It was coincidence.

## Practical rule

- Treat any bench difference under about **5% as noise**.
- Quote the between-launch spread rather than `llama-bench`'s reported sigma.
- Interleave arms as A/B/A/B rather than running them in sequence.
