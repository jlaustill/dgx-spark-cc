# X1 — the resident-model ratio

**Question.** With one model held **entirely in fast memory on both machines**,
how much faster is mira than spark?

**Why it matters.** Every cross-box number so far has mira reaching across
DDR5-3600 at ~58 GB/s for MoE experts it had nowhere to put, because 16 GB of
VRAM cannot hold an 80B model. Those runs measure the *offload penalty*, not the
*hardware*. See [findings/mira/04](../../findings/mira/verified/04-the-spark-wins-both-halves-on-qwen3-next.md).

The decision this feeds: **VRAM on mira is upgradeable; the Spark's 121 GB is
not.** If mira is >=2x faster once memory stops being the constraint, buying a
larger card converts that into a real advantage. So we need the ratio with no
offload and no extrapolation.

Two earlier attempts to shortcut this failed and are why the protocol is written
out rather than improvised:

- A **synthetic prompt** inflated mira's prefill 69% and produced a crossover
  rule that did not exist —
  [findings/mira/03](../../findings/mira/verified/03-repetitive-prompts-inflate-offloaded-moe-prefill.md).
- **Extrapolating** the `--n-cpu-moe` curve to full residency implied a negative
  fixed cost, which is impossible, so the extrapolation was discarded.

## The model, and why this one

`gpt-oss-20b-MXFP4.gguf`, **11.27 GiB**, from `ggml-org/gpt-oss-20b-GGUF`.

It is the only interesting model that fits in mira's ~15.8 GiB with room for a
KV cache at depth, and spark holds it trivially in 121 GB. So it is the one
model on which **neither box has to offload anything.** That is the entire point:
any model where mira offloads measures the DDR5 tier instead of the GPU.

Quality is irrelevant here. gpt-oss silently drops mid-conversation system
messages ([findings/spark/15e](../../findings/spark/verified/15e-gpt-oss-drops-mid-conversation-system-messages.md))
and is unfit for agentic work — but this is a throughput measurement, and that
defect does not touch throughput.

## Preconditions

`run.sh` checks all of these and refuses if any fails.

| | why refusing matters |
|---|---|
| llama.cpp at **`687e778`** | every number in this repo is on it; another commit is not comparable |
| model sha256 `27cd6c43...` | a truncated GGUF still loads and still benches |
| **no llama-server running** | a loaded production server contends for bandwidth and quietly depresses the result |
| all layers on GPU, `n_cpu_moe = 0` | if anything offloads, this measures the wrong thing |
| GPU idle before start | see [findings/spark/08b](../../findings/spark/verified/08b-the-bench-noise-floor-is-4-percent.md) |

**On spark you must stop the production server first.** `V7.4` did exactly this
("V4 production server stopped for the duration and restored afterwards") and it
is the difference between a real number and a contended one.

## Running it

```bash
./run.sh                 # auto-detects the machine, checks, benches, writes results/<machine>.json
./run.sh --download      # same, but fetch the model first if absent (11.27 GiB)
```

Overrides, if auto-detection is wrong:

```bash
X1_MACHINE=spark X1_LLAMA=~/llama.cpp X1_MODEL=/path/to/gpt-oss-20b-MXFP4.gguf ./run.sh
```

## What it measures

Two independent process launches — not two reps inside one — because
[findings/mira/05](../../findings/mira/verified/05-back-to-back-launch-variance.md)
shows within-run sigma understates true spread.

```
-p 4096 -n 128 -d 0,16384,65536 -ngl 99 -fa on -r 3 -o json
```

Depth matters: decode decays as KV grows, and the two boxes may decay at
different rates. A single shallow number would hide that.

## When it is done

Both files exist:

```
results/mira.json      <- produced on mira
results/spark.json     <- produced on spark
```

Then, from either box:

```bash
./compare.py
```

which prints the ratio table and writes nothing. Commit the JSON; it is raw
measurement and belongs in the repo.

## Reporting back

Commit `results/<machine>.json` and push. The other box picks it up with
`git pull`. If you cannot push, paste the JSON — it is self-describing and
carries its own machine, GPU, commit and model hash.
