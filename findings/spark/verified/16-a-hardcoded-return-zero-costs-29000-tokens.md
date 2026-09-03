---
id: "16"
status: verified
title: One hardcoded return 0 costs about 29,000 tokens per session
measured: 2026-08-17
see_also: ["11b", "15a"]
---

# One hardcoded return 0 costs about 29,000 tokens per session

**Claim.** When the head of the prompt changes, the server does not reuse the
prefix of about 9,700 tokens that it still holds. It resets to zero.

The cause is one hardcoded return at `llama-model.cpp:2506-2512`:

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

## That single return does three things at once

1. **It disables `--swa-full`.** `server-context.cpp:1296-1299` gates the
   rejection on `llama_model_n_swa() == 0`. The server logs `swa_full is not
   supported by this model, it will be disabled`.
2. **It makes the reuse threshold maximally strict.**
   `server-context.cpp:3299` computes `pos_min_thold = pos_next - n_swa - ...`.
   With `n_swa = 0` the threshold becomes `pos_next` itself, which is **stricter**
   than the real 128-token window.
3. **It blocks context-checkpoint creation.** Creation requires
   `seq_rm_type in {FULL, RS} || n_swa > 0`, at `server-context.cpp:3468-3475`.
   The checkpoint search therefore falls through to `do_reset`, which sets
   `n_past = 0`.

**The reset is not caused by the sliding window being small. It is caused by the
server being told there is no window at all.** That removes both the workaround
flag and the checkpoint fallback that would have covered it.

## Magnitude

This is worth about **29,000 tokens per session**. That is small beside the
436,814 tokens attributed to
[15a](15a-a-trailing-system-message-rewrites-the-head.md).

It is a one-line upstream diagnosis. Unlike the abandoned cache-shifting work, it
requires no new compressed-cache code.

## Also worth reporting upstream

`llama_kv_cache_iswa` logs `using full-size SWA cache` **before** the server
disables the flag. The memory appears to be allocated and the benefit is then
discarded.
