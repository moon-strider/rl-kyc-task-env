# Comparing extraction pipelines on fresh synthetic documents

This experiment connects the existing NER and Swarm services to the KYC scoring
environment. It compares the unchanged heuristic, direct model extraction, a
same-model ensemble and a grounded entity-to-fields pipeline. A separate,
development-only prompt search evaluates up to two instruction candidates.

The experiment uses real local CPU inference, without API keys or model weight
training. It is a small engineering experiment, not a production KYC accuracy
claim or a GEPA reproduction. The earlier negative Qwen2.5 experiment remains
unchanged in [experiment.md](experiment.md).

## Methods

| Method | Upstream requests per successful document | Behavior |
| --- | ---: | --- |
| Heuristic | 0 | Existing baseline reads the original OCR JSON without changes. |
| Direct | 1 | Qwen3-4B produces the full schema, with string/null fields and constrained JSON output. |
| Swarm | 3 | Two samples of the same Qwen model at temperatures 0 and 0.4, followed by a temperature-0 merger. Both generators must succeed. |
| NER | 1 | The actual NER service extracts role-specific entities and exact source offsets; an adapter maps them to all KYC schema fields. |

Every model method receives the same OCR text and page/block/line coordinates.
No method receives rendered pixels or gold answers during evaluation. Direct and
Swarm use the same extraction prompt and output schema. The client deliberately
omits request-level temperature for Swarm, preserving its generator settings.

NER labels distinguish the identity holder from the issuer, the customer from
the statement provider, and the payer from the recipient. Missing entities become
null. Different grounded values for one role also produce null; identical repeated
values agree. Invalid labels, offsets or overlapping entity spans fail validation.
Normalization for scoring uses the environment's existing canonicalizer.

NER remains a different pipeline: exact grounding limits invented entity text,
but can preserve damaged OCR characters or reject normalized text that no longer
matches the source. Its role definitions and surface constraints are part of the
method, rather than a claim that generic entity recognition is a complete KYC parser.

The comparison holds documents, underlying model weights and per-call output
limits fixed, not total inference budgets. Swarm spends up to three calls on a
document; NER has its own role descriptions, entity output schema and mapping
rules. Differences therefore measure these complete pipelines, not the isolated
effect of an ensemble or of entity recognition. The ensemble's two samples share
model weights, so their errors need not be independent.

## Frozen protocol

1. Freeze source hashes, dataset rules, request templates, service configurations,
   model identity, budgets and selection rules before creating development data.
2. Generate nine noisy development documents, using three public template families
   per schema and seed 2026091301.
3. Evaluate all four methods on those same documents.
4. Optimize only the direct-model prompt. Each of at most two rounds sees the
   current development errors, at most one highest-error document per schema,
   and previous candidate prompts/scores. The model proposes an instruction
   addendum of at most 200 words. Incomplete, oversized or duplicate candidates
   are rejected; other candidates are evaluated on all nine development documents.
5. Select only a strictly higher official development score. Ties retain the
   incumbent. Save the chosen prompt hash and selection record before generating
   any holdout data.
6. Generate 24 holdout variants with seed 2026091302: six additional template
   families, two independently sampled base documents per family, each rendered
   as paired clean and noisy OCR. One base per family has an identifier/postal-code
   value removed before rendering, with only that gold field changed to null.
7. Evaluate the original four methods and, if different, the selected prompt on
   the same holdout inputs. No holdout-driven prompt changes or method selection
   are performed.

The 24 variants represent **12 independent base documents**, not 24 independent
samples. Clean/noisy pairs share identical gold. Group, seed and missing-field
metadata remain outside model inputs.

All template source code is public. "Holdout" means excluded from prompt tuning;
it does not mean secret templates or a protected external test set. Published
evidence is unsuitable as a future private benchmark without new data and seeds.

The budget is at most 209 upstream requests: 165 for four methods across both
splits, up to 20 for two reflection/development rounds, and 24 for a changed
selected prompt on holdout. If the original prompt remains selected, its holdout
results are reused without inventing another set of calls. A separate fixed
toy-receipt preflight uses five requests to check the three service paths.

## Measurement and evidence

The official scorer evaluates complete frozen prediction envelopes. An invalid
record receives zero, including when the expected value is null; failures never
remove documents from the denominator. Reports include:

- Official score, canonical field accuracy and exact documents.
- Results by schema, template and OCR profile; paired clean/noisy field changes.
- Missing-value abstention, hallucinated non-null values and invalid outputs.
- Per-document latency, mean/median/p95 and total request time.
- Reported usage/calls and independently observed upstream requests/tokens.
- Truncation and failures from every upstream response, including responses hidden
  by a failing NER or Swarm service envelope.

The official score averages `0.9 * field_accuracy + 0.1 * exact_document`
within each schema, then gives the three schemas equal weight. The separate
overall field accuracy is a micro-average across all fields. These quantities
can differ; prompt selection uses the official score only.

A recording proxy sits between the services and llama.cpp. It saves the exact
request/response bodies, their hashes, status, duration and document attribution.
The proxy excludes authorization headers. Unknown usage stays unknown, never
silently zero. Observed request counts include failed attempts if any occur.

Requests run serially through one CPU server: heuristic, direct, Swarm, then NER
for each split, with documents in manifest order. Swarm's upstream calls also
run one at a time. Timings include service overhead and depend on the warm prompt
cache; no randomized ordering or cache-reset trial is performed. They are
observations of this setup, not controlled latency rankings on other hardware.
Model download, loading and service startup are outside per-document latency.

The local runner executes only trusted repository code. It is separate from the
[Docker boundary for untrusted participant submissions](isolation.md); collector
and scorer isolation are unchanged.

## Reproduce

Use Python 3.12 and the locked environments. Install the two services in separate
checkouts because their pinned dependencies differ:

~~~bash
git clone https://github.com/moon-strider/ner ../ner
git -C ../ner checkout 22a86d8cf1af451f15e03d75a5f204c5fb2da1fc
uv --directory ../ner sync --frozen --python 3.12 --no-dev

git clone https://github.com/moon-strider/swarm-of-experts ../swarm-of-experts
git -C ../swarm-of-experts checkout cc475251528cf986186cdf3b3b8a423da8269388
uv --directory ../swarm-of-experts sync --frozen --python 3.12 --no-dev

uv sync --frozen
~~~

The model is [Qwen3-4B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507),
with the [Unsloth Q4_K_M quantization](https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/resolve/a06e946bb6b655725eafa393f4a9745d460374c9/Qwen3-4B-Instruct-2507-Q4_K_M.gguf).
Its SHA-256 is
3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597.
The runner uses llama.cpp b10867, commit f3f1a8f27, six CPU threads,
a 16,384-token context, one slot and no GPU layers. The executable, model,
service commits and exact command lines are recorded with each run.

Run the fixed preflight in a new output directory:

~~~bash
uv run --frozen python scripts/run_comparison.py /tmp/kyc-preflight \
  --runner /absolute/path/to/llama-server \
  --model-file /absolute/path/to/Qwen3-4B-Instruct-2507-Q4_K_M.gguf \
  --ner-repo ../ner \
  --swarm-repo ../swarm-of-experts \
  --preflight-only
~~~

Then run the frozen comparison with a different new directory:

~~~bash
uv run --frozen python scripts/run_comparison.py /tmp/kyc-comparison \
  --runner /absolute/path/to/llama-server \
  --model-file /absolute/path/to/Qwen3-4B-Instruct-2507-Q4_K_M.gguf \
  --ner-repo ../ner \
  --swarm-repo ../swarm-of-experts \
  --reflection-rounds 2
~~~

The runner starts and stops all services itself in one process tree and network
namespace. It neither downloads models nor contacts a paid provider. Existing
output directories are rejected. Source changes after protocol freeze stop the
experiment. Per-document predictions and traces are written as work progresses;
failures retain evidence, and all retained non-runtime artifacts receive checksums.

The dataset and adapters can also be used independently through
rl_kyc_task_env.comparison_dataset and rl_kyc_task_env.comparison. The full runner
requires the source checkouts and external model executable. Wheels and source
distributions continue to exclude datasets and gold answers.
