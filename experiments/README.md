# Experiments

Runnable, cross-machine protocols. Each directory is self-contained: a protocol,
a runner that checks its own preconditions, and a place for results.

**These exist because the study spans two machines that cannot see each other.**
A session on one box has to be able to run its half without having been present
for the other half. So each experiment states what it is for, refuses to run if
its preconditions are unmet, and writes a fixed-schema JSON that a comparison
script can read without a human in the middle.

| id | question | status |
|---|---|---|
| [X1](X1-resident-model-ratio/) | With the model fully resident on both boxes, what is the decode/prefill ratio between them? | **done** — mira 2.1-2.4x prefill, 3.1-3.5x decode ([mira/06](../findings/mira/verified/06-with-no-offload-mira-is-2-to-3-5x-faster.md)) |

## If you are an agent picking this up cold

Read the experiment's own `README.md` first — it names its preconditions and what
"done" means. Then run `./run.sh`. It will tell you what is missing rather than
produce a number that looks fine and is not.

Do not "fix" a failing precondition by relaxing it. Every check in these runners
is there because getting it wrong produces a plausible wrong answer rather than
an error. See [../NOTES.md](../NOTES.md).
