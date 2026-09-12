# A real local-model OCR extraction experiment

This repository includes actual CPU inference from **Qwen2.5-1.5B-Instruct
Q4_K_M**, the unchanged heuristic baseline, and a failed one-step automatic
prompt-reflection attempt. No API key, paid inference, mock responses, or model
weight training was used. The small experiment is a reproducible engineering
case, not evidence about production KYC accuracy.

The complete [evidence directory](evidence/qwen-cpu-20260912/) contains the
synthetic input OCR, separate gold JSON, input hashes, prompts, raw responses,
prediction envelopes, per-document errors, timing, tokens, server logs and
[model/runtime provenance](evidence/qwen-cpu-20260912/provenance.json).

## Protocol

1. Generate **9 development documents**, three per schema, with seed
   `2026091201`. All use the existing standard OCR noise; each schema uses its
   first three public template families.
2. Run the fixed heuristic and a short direct extraction prompt on those inputs.
3. Give the same local model only development OCR, failed predictions and their
   expected values. Ask for one general instruction addendum. Keep the resulting
   candidate, including a bad candidate, and evaluate it on development data.
4. Freeze the direct and reflected prompt hashes in
   [freeze.json](evidence/qwen-cpu-20260912/freeze.json).
5. Only then generate **12 fresh holdout documents**, four per schema, using
   seed `2026091202`. Each schema uses its fourth public template family, which
   was withheld from prompt tuning. Six documents have clean OCR and six have
   the existing standard OCR noise. Evaluate all methods on these same inputs.

The input representation is OCR only: text grouped by page, block and line,
with x/y positions. It uses the same geometric token joining as the heuristic;
there is no answer-derived OCR correction. The heuristic receives the original
OCR JSON. The generator's rendered image is clean even when its OCR is damaged;
no method in this experiment receives image pixels. The new holdout template
families are present in the public source code, so this is a **template holdout
for prompt tuning**, not a secret benchmark unseen by all baseline authors.

The automatic method takes the idea of diagnosing execution errors from
[GEPA](https://arxiv.org/abs/2507.19457v2). It has **one reflection call**, no
population, Pareto selection, crossover, multiple search rounds, or training of
weights. It is neither a GEPA implementation/reproduction nor an RL experiment.

## What happened

The reflection model returned a JSON object that simply repeated the direct
prompt. We appended this returned text as specified by the protocol and retained
the degradation. It was not silently replaced or tuned on holdout errors.

| Automatic protocol, holdout | Correct fields | Exact documents | Official score | Invalid predictions | Mean inference/document |
| --- | ---: | ---: | ---: | ---: | ---: |
| Unchanged heuristic | 70/76 (92.1%) | 7/12 | 0.8851 | 0 | 0.003 s |
| Direct Qwen | 60/76 (78.9%) | 6/12 | 0.7679 | 0 | 6.31 s |
| One automatic reflection | 50/76 (65.8%) | 5/12 | 0.6452 | 1 | 6.20 s |

Development scores were 51/57 fields for the heuristic, 49/57 for direct Qwen,
and 36/57 for the reflected prompt. The reflected variant had two invalid
development predictions (one schema violation and one truncated input echo)
and one invalid holdout prediction (extra fields). Invalid predictions receive zero
credit, including when a gold field happens to be null.

The direct model was strongest on government IDs (24/24 holdout fields), but
confused issuer/customer or payer/payee roles in the development documents.
The heuristic remained a strong and much faster baseline on this synthetic
distribution. These results do not support a claim that automatic reflection
improved this task.

## Additional exploratory prompt

After the failed automatic reflection, an analyst wrote **one additional
prompt** from the direct model's development errors: distinguish the customer's
address from the issuer's address, identify payer versus payee, and preserve
column/block associations. This was a separate manual intervention, not output
from the automatic optimizer.

The [prompt](evidence/qwen-cpu-20260912/dev-guided-prompt.txt) and its
[freeze record](evidence/qwen-cpu-20260912/dev-guided-freeze.json) were written
**after holdout generation but before inspecting any holdout model answers**.
No further candidate or revision was made. Because this timing differs from the
main protocol, its measurements are reported separately as exploratory.

Its complete development and holdout results are in
[dev-guided/metrics.json](evidence/qwen-cpu-20260912/dev-guided/metrics.json) and
[holdout-guided/metrics.json](evidence/qwen-cpu-20260912/holdout-guided/metrics.json).
It reached **50/57 development fields and 7/9 exact documents**, but only
**39/76 holdout fields (51.3%) and 4/12 exact documents**. All four holdout
government-ID responses echoed the input instead of extracting fields and were
truncated at 512 tokens; they correctly received zero credit. This additional
negative result illustrates how a plausible instruction change can help one
small development set while breaking output behavior on held-out templates.

The freeze record's original `dev_metrics_sha256` refers to the immutable
[metrics snapshot used for that decision](evidence/qwen-cpu-20260912/reflection/dev-direct-metrics-at-guided-freeze.json).
The current metrics files were subsequently rescored with explicit truncated
response counts; no prompts or model predictions were changed.

## Scoring and costs

`infer` only opens each input directory's `meta.json` and `ocr.json`. It never
loads `target.json`, images or the sibling gold directory. Model requests and
raw outputs are saved before the scorer reads gold. Frozen envelopes are loaded
through the same bounded strict parser as the trusted judge; inference code is
not executed during scoring.

Field accuracy is the micro-average across 76 fields. Exact documents require
every field to match after the repository's canonicalization. The official
score is the schema-macro average of `0.9 * field_accuracy + 0.1 * exact_doc`.
They are different metrics and should not be substituted for one another.

Direct holdout inference used 10,285 prompt tokens and 1,230 completion tokens.
The reflected holdout used 11,029 and 1,265. The single reflection call itself
used 3,332 prompt and 63 completion tokens and took 21.77 seconds. The separate
exploratory run reports its own usage. Timings are wall clock per endpoint
request, exclude model download/build/loading, and include server prompt-cache
behavior. Monetary cost is left null: no provider was billed and electricity or
hardware costs were not measured.

## Reproduce

Install the project with its pinned lock (`uv sync --frozen`). The model is from
the [official Qwen publisher](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/tree/91cad51170dc346986eccefdc2dd33a9da36ead9),
with SHA-256
`6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e`.
The CPU runner is
[llama.cpp at 3057bb6](https://github.com/ggml-org/llama.cpp/commit/3057bb66c86c46d5781e50e85462a760ba7d1feb).

With Git, CMake, a C++ compiler, OpenSSL development headers and Python 3.12+
installed, build and launch the pinned runner in a cache outside the repository:

```bash
bash scripts/local_model.sh /tmp/kyc-model-cache
```

In another terminal, run the main protocol into a **new** output directory:

```bash
uv run python scripts/run_experiment.py /tmp/kyc-reproduction
```

To replay the already published exploratory prompt as well:

```bash
uv run python scripts/run_experiment.py /tmp/kyc-reproduction-with-exploration \
  --exploratory-prompt docs/evidence/qwen-cpu-20260912/dev-guided-prompt.txt
```

For environments that isolate localhost per process tree, the runner can launch
the already built server as a child, wait for readiness and close it on exit:

```bash
uv run python scripts/run_experiment.py /tmp/kyc-reproduction-one-process-tree \
  --runner /tmp/kyc-model-cache/llama.cpp/build/bin/llama-server \
  --model-file /tmp/kyc-model-cache/qwen2.5-1.5b-instruct-q4_k_m.gguf
```

Individual generate/infer/reflect/score stages are available through
`rl-kyc-experiment --help`. An explicitly configured OpenAI-compatible endpoint
may be used; remote endpoints require HTTPS. Optional credentials are read from
`KYC_MODEL_API_KEY`, never command-line key values or trace metadata.

Scoring the published model predictions requires **no model or network**:

```bash
uv run rl-kyc-experiment score \
  --dataset docs/evidence/qwen-cpu-20260912/holdout \
  --run docs/evidence/qwen-cpu-20260912/holdout-direct

uv run rl-kyc-hidden-judge \
  --predictions docs/evidence/qwen-cpu-20260912/holdout-reflected/predictions.json \
  --dataset-dir docs/evidence/qwen-cpu-20260912/holdout/inputs \
  --gold-dir docs/evidence/qwen-cpu-20260912/holdout/gold
```

## Limits

Only 12 holdout documents and one small quantized model were evaluated. There
are no uncertainty estimates or claims of statistical significance. The six
clean and six noisy documents have different values; their stratified scores
are descriptive, not a paired causal estimate of OCR degradation. No real
identity documents were used. Corrupted or deleted OCR can remove evidence
permanently; exact hidden values cannot always be recovered from text alone.
The experiment tests extraction, not fraud detection or identity verification.

Original generation used Pillow 12.2.0; the final pinned environment uses
12.3.0. The [regeneration check](evidence/qwen-cpu-20260912/regeneration-check.json)
records comparisons of the saved OCR, gold and manifest hashes. Exact model
outputs and especially wall times may vary with CPU/backend behavior even with
temperature zero and a fixed seed; the saved predictions are the authoritative
record of this run.
