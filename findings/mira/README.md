# Findings — mira

`linux-Thelio-Mira`. RTX 5070 Ti (GB203, 16 GB GDDR7) + Ryzen 9 7950X3D +
124 GB DDR5-3600, x86_64. llama.cpp pinned at `687e778`, the same commit as
[spark](../spark/), so numbers from the two trees are comparable.

One claim per file. **The directory is the status.**

## The one sentence the rest of this follows from

This box is the Spark inverted. It has roughly 3.3x the memory bandwidth over
1/8th the capacity, and the two pools are separate rather than unified. Almost
nothing worth running fits in 16 GB, so **offload is not a tuning option here,
it is the operating mode.** See [01](verified/01-bandwidth-for-capacity.md).

## Start here

The measurement that changed a conclusion:
[03](verified/03-repetitive-prompts-inflate-offloaded-moe-prefill.md).

<!-- BEGIN INDEX -->

### verified (5)

Survived a deliberate attempt to falsify it.

- **[01](verified/01-bandwidth-for-capacity.md)** — An RTX 5070 Ti buys memory bandwidth and pays with capacity
- **[03](verified/03-repetitive-prompts-inflate-offloaded-moe-prefill.md)** — A repetitive prompt inflates offloaded-MoE prefill by 69 percent
- **[04](verified/04-the-spark-wins-both-halves-on-qwen3-next.md)** — The Spark beats this box on both halves of a turn for Qwen3-Next-80B
- **[05](verified/05-back-to-back-launch-variance.md)** — Back-to-back launch variance here is 0.45 percent, and is not spark's 4.3
- **[06](verified/06-with-no-offload-mira-is-2-to-3-5x-faster.md)** — With nothing offloaded, mira is 2.1-2.4x on prefill and 3.1-3.5x on decode

### unverified (1)

Measured once. Not yet re-tested against a falsification attempt. Each file names the test that would close it.

- **[02](unverified/02-moe-offload-is-linear-with-no-knee.md)** — MoE expert offload is linear in the fraction offloaded, with no knee

### refuted (0)

Tested and found false. Kept because each one is still reachable by plausible reasoning, and because acting on it costs real time.


<!-- END INDEX -->
