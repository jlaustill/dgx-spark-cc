# E5 test plan — the rope-stretch tolerance threshold

Mode: Strict ASD-STE100. Lexical rules are a direction of travel, not dictionary
compliance.

## 1. The question

E5 asks where the rope-stretch tolerance threshold is.

V9.2 already showed that a stretch destroys output at the context ceiling. On
gpt-oss-120b at 131,072 tokens, `--rope-scale 2` moved perplexity from 2.7940 to
94.4541. This is a 34x increase.

V9.2 did not find the threshold. It tested two points only. The two points were
1.0 and 2.0. E5 must find the value where the damage starts.

V9.2 also showed that the damage depends on depth. At 2,048 tokens the same flag
improved perplexity by 3.5%. A threshold in stretch factor alone is therefore not
sufficient. The test must sweep two variables.

## 2. What the test measures

The test measures perplexity. Perplexity on this harness is deterministic. A
repeat run gave the same value to four decimal places. Any change in perplexity
is caused by the changed variable and nothing else.

The test sweeps two variables:

- stretch factor: 1.0, 1.25, 1.5, 2.0, 4.0
- context depth: 8,192, 32,768, 131,072

The plan first listed 262,144 as a fourth depth. That depth is not possible on
this machine. `llama-perplexity` holds the logits for the full context. The
buffer is `n_ctx x n_vocab x 4` bytes. Qwen has a vocabulary of 151,936 tokens.
A context of 262,144 tokens therefore needs 148.4 GiB. The machine has 121 GB.
The run fails with `std::bad_alloc`. A context of 131,072 tokens needs 74.2 GiB
and is the deepest that fits.

## 3. The model to use

Use Qwen3-Coder-30B-A3B-Instruct-Q8_0.

Three reasons support this choice:

1. Its native window is 262,144 tokens. This is the largest native window of the
   three models on disk.
2. It is 30.3 GB. It loads faster than the other two models.
3. It has no vendor YaRN configuration. gpt-oss-120b ships YaRN at factor 32.
   A stretch on gpt-oss therefore stacks a second YaRN on the first. A stretch on
   Qwen applies one scaling only.

The third reason is the important one. E5 must measure one variable. gpt-oss
cannot give a clean answer.

## 4. Prerequisites

1. Stop the server. The eval finished. The box must be free.
2. Build a corpus of at least twice the deepest context. `llama-perplexity`
   refuses a run when the corpus holds fewer than 2 x `-c` tokens. A test at
   262,144 tokens therefore needs 524,288 tokens. An earlier version of this
   plan said 300,000 tokens. That number was wrong and the 262,144 row failed
   on it.
3. Confirm that the corpus is not code that the model memorized. Use prose.

## 5. Procedure

Run one perplexity pass for each pair of stretch factor and depth.

1. Set the stretch factor with `--rope-scaling yarn --rope-scale N`.
2. Set the depth with `-c N`.
3. Use `--chunks 1`. One chunk at full depth measures the deep positions.
4. Record the perplexity value.
5. Repeat for all 20 pairs.

Use the same corpus file for every pass. Use the same model file for every pass.

## 6. The registered outcome

Write the expected result before the test runs.

- If perplexity stays flat up to some factor and then rises, that factor is the
  threshold.
- If perplexity rises from factor 1.25 at every depth, there is no safe stretch.
- If perplexity rises only at the deepest context, the threshold depends on
  depth. Report it as a curve, not a number.

A flat result at all 20 points would contradict V9.2. Treat that outcome as a
harness fault. Check the flag first. Do not report it as a finding.

## 7. What this test cannot answer

The test measures perplexity on one corpus. Perplexity is not task success.

The document compares two models by base length and stretch factor:

| Model | Base | Factor | Result |
|---|---:|---:|---|
| DeepSeek V4 Flash | 65,536 | x16 | 1M |
| gpt-oss-120b | 4,096 | x32 | 131k |

This test does not compare those two models. It sweeps one model. A cross-model
claim needs a separate test. That test has a confound: the two models differ in
weights, in architecture, and in training data.

## 8. Cost

Each pass at 262,144 tokens takes about 5 minutes. Each pass at 8,192 tokens
takes under 1 minute. The model load takes about 2 minutes.

The full sweep of 20 pairs takes about 2 hours.

## 9. Optional second stage

Run the eval harness against the best and worst stretch factors. The harness
scores 10 real tasks. This converts a perplexity curve into a task-success
number.

This stage costs about 3 hours per arm. Run it only if stage 1 finds a
threshold.
