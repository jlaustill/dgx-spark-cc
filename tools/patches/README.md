# Local llama.cpp patches

Every number in this repo is on llama.cpp `687e778`. These are the deviations
from that commit, kept here so the build is reproducible and so nothing sits
untracked in the checkout.

Apply against a clean `687e778`:

```bash
cd /home/linux/llama.cpp
git apply /home/linux/code/dgx-spark-cc/tools/patches/*.patch
cmake --build build --config Release -j "$(nproc)" --target llama-server
```

| patch | what | inert by default? |
|---|---|---|
| `v71-no-blackwell-mma.patch` | `GGML_NO_BLACKWELL_MMA` ablation switch used by V7.1 to isolate the native FP4 path. Guards the device selector and the host selector from one flag so they cannot desynchronise. | yes — compile-time, undefined in normal builds |
| `e8-allow-ctx-overflow.patch` | `LLAMA_ALLOW_CTX_OVERFLOW` lifts the unconditional slot-context cap at `server-context.cpp:1310`, which otherwise blocks a correctly rope-scaled config from serving past `n_ctx_train`. | yes — runtime env var, unset in normal use |

Neither changes behaviour unless explicitly switched on. `build-llamacpp.sh` runs
`git pull --ff-only` and will move the checkout off `687e778` — do not run it if
you intend to reproduce these numbers.
