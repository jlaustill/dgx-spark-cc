---
id: "00"
status: verified
title: A DGX Spark buys memory capacity and pays with memory bandwidth
measured: 2026-08-10
see_also: ["06a", "17"]
---

# A DGX Spark buys memory capacity and pays with memory bandwidth

**Claim.** The GB10 holds 121 GB of unified LPDDR5X and moves bytes at about
273 GB/s. That is roughly a quarter of the bandwidth of a dedicated card. Every
other finding in this set follows from that one trade.

## Evidence

| | Bandwidth | Capacity |
|---|---:|---:|
| **GB10 (this box)** | ~273 GB/s | **121 GB** |
| RTX 5090 | ~1,800 GB/s | 32 GB |
| H100 | ~3,350 GB/s | 80 GB |

The capacity holds a 284B-parameter model with a million tokens of context. No
consumer GPU can do this.

Unified memory removes one of the two data movements a normal GPU pays. There is
no PCIe copy from system RAM into VRAM. There are no offload decisions. There is
no question of whether the model fits on the card. Unified memory cannot remove
the second movement, which is DRAM into the compute circuits. That movement is
what memory bandwidth measures.

The trade creates an asymmetry between the two phases of inference:

- **Prefill batches.** One read of the weights serves thousands of tokens, so the
  memory pipe stays about 94% idle. Prefill is compute-bound.
- **Decode cannot batch.** You cannot group a token that the model has not
  generated yet. Every token pays a full read of the weights, so decode runs into
  the bandwidth limit.

## The machine

| | |
|---|---|
| Host | `gx10-52c8`, NVIDIA DGX Spark (GB10) |
| Compute capability | **12.1** (Blackwell) |
| Memory | 121 GB unified LPDDR5X, ~273 GB/s theoretical |
| Arch / toolchain | aarch64, CUDA 13.0, gcc 13.3 |
| Storage | NVMe, ~3.7 GB/s observed writes |
| llama.cpp | pinned at `687e778` |

## Limits

There is no single measured bandwidth figure for this box. Qwen achieves
221 GB/s and gpt-oss achieves 143 GB/s on the same hardware. See
[06a](06a-shallow-decode-is-bandwidth-bound.md) and
[07b](../refuted/07b-mxfp4-outdecodes-q8-0.md) for why the two differ.

Every number in this finding set is on llama.cpp commit `687e778`. The script
`build-llamacpp.sh` runs `git pull --ff-only`, which moves the checkout and
makes the numbers no longer comparable.
