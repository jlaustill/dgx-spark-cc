---
id: "09a"
status: verified
title: The server caps context but does not reset the rope parameters
measured: 2026-08-17
see_also: ["09b", "09c"]
---

# The server caps context but does not reset the rope parameters

**Claim.** `llama-server` caps a requested context back to the trained context
and emits only a warning. It does not reset the rope parameters at the same time.
The server then looks healthy while the positional encoding is wrong.

## Evidence

The upstream config for gpt-oss-120b:

```json
"rope_scaling": {"rope_type":"yarn","factor":32.0,
                 "original_max_position_embeddings":4096}
```

4096 x 32 = 131,072. The model's window is **already** the YaRN-extended one.
Asking for more stacks a second YaRN on top of the first.

`server-context.cpp:1311-1313` caps `n_ctx_slot` back to `n_ctx_train` with only
a warning. `llama-context.cpp:130-132` resolves `n_ctx` and the rope parameters
from **independent ternaries**:

```c
cparams.n_ctx           = params.n_ctx           == 0    ? hparams.n_ctx_train          : params.n_ctx;
cparams.rope_freq_base  = params.rope_freq_base  == 0.0f ? hparams.rope_freq_base_train : params.rope_freq_base;
cparams.rope_freq_scale = params.rope_freq_scale == 0.0f ? hparams.rope_freq_scale_train: params.rope_freq_scale;
```

Nothing resets the rope parameters when the context is capped.

## The rule

**Run at the vendor's declared `max_position_embeddings`. Never pass rope flags
yourself.**

## Limits

The capping behaviour is specific to `llama-server`, at
`server-context.cpp:1311-1313`. `llama-perplexity` at `-c 262144` only warns, with
`n_ctx_seq (262144) > n_ctx_train (131072) -- possible training context
overflow`, and then proceeds at the requested size.

Note also that `--cache-reuse` is disabled automatically under sliding-window
attention. The server logs this, and the line is easy to miss.

For the size of the damage, see
[09b](09b-rope-mismatch-costs-34x-perplexity.md).
