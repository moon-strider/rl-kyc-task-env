# Comparing extraction pipelines on fresh synthetic documents

This experiment connects the existing NER and Swarm services to the KYC scoring
environment. It compares the unchanged heuristic, direct model extraction, a
same-model ensemble and a grounded entity-to-fields pipeline. A separate,
development-only prompt search evaluates up to two instruction candidates.

The experiment uses real local CPU inference, without API keys or model weight
training. It is a small engineering experiment, not a production KYC accuracy
claim or a GEPA reproduction. The earlier negative Qwen2.5 experiment remains
unchanged in [experiment.md](experiment.md).

## Recorded holdout results

The unchanged heuristic has the highest score on this run. NER is the strongest
of the three model pipelines on holdout; it was weaker on development. Neither
result establishes a general ranking beyond these synthetic documents.

| Method | Score | Correct fields | Exact docs | Correct nulls | Calls | Total tokens | Mean seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [Heuristic](evidence/comparison-cpu-20260913/holdout-heuristic/metrics.json) | 0.9298 | 145/152 | 17/24 | 12/12 | 0 | 0 | 0.005 |
| [Direct / selected](evidence/comparison-cpu-20260913/holdout-direct/metrics.json) | 0.8503 | 136/152 | 11/24 | 8/12 | 24 | 15,741 | 16.474 |
| [Swarm](evidence/comparison-cpu-20260913/holdout-swarm/metrics.json) | 0.8598 | 137/152 | 12/24 | 8/12 | 72 | 53,360 | 32.922 |
| [NER](evidence/comparison-cpu-20260913/holdout-ner/metrics.json) | 0.8893 | 139/152 | 15/24 | 10/12 | 24 | 20,019 | 22.817 |

These are 24 clean/noisy variants of **12 independent base documents**. All
outputs are valid; no upstream request failed or was truncated. The selected
prompt is the original direct prompt, so its results and costs are reused once.
Both proposed prompt changes lost on development and were rejected before
holdout generation.

The complete experiment used **185 upstream requests and 143,218 tokens**,
including both reflection proposals and both nine-document candidate evaluations.
The five-call preflight is separate. No dollar cost is inferred from local CPU
usage. See the [full summary](evidence/comparison-cpu-20260913/results.json),
[dataset integrity audit](evidence/comparison-audit-cpu-20260913/dataset.json)
and [independent request audit](evidence/comparison-audit-cpu-20260913/proxy.json).

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

## Development results and prompt selection

The nine development documents contain 57 scored fields. All six extraction
runs below returned valid predictions without truncated upstream responses.
The call counts exclude the two separate calls that proposed the candidates.

| Development method | Correct fields | Exact documents | Official score | Upstream calls | Mean seconds/document |
| --- | ---: | ---: | ---: | ---: | ---: |
| [Unchanged heuristic](evidence/comparison-cpu-20260913/dev-heuristic/metrics.json) | 49/57 | 3/9 | 0.8095 | 0 | 0.007 |
| [Direct Qwen3](evidence/comparison-cpu-20260913/dev-direct/metrics.json) | 51/57 | 5/9 | 0.8579 | 9 | 18.24 |
| [Swarm](evidence/comparison-cpu-20260913/dev-swarm/metrics.json) | 51/57 | 5/9 | 0.8579 | 27 | 32.55 |
| [NER pipeline](evidence/comparison-cpu-20260913/dev-ner/metrics.json) | 44/57 | 4/9 | 0.7540 | 9 | 25.62 |
| [Prompt candidate 1](evidence/comparison-cpu-20260913/dev-candidate-1/metrics.json) | 50/57 | 5/9 | 0.8508 | 9 | 19.07 |
| [Prompt candidate 2](evidence/comparison-cpu-20260913/dev-candidate-2/metrics.json) | 50/57 | 5/9 | 0.8508 | 9 | 19.47 |

Swarm matched the direct method's development score while using three times as
many upstream calls. Both prompt candidates scored below the direct incumbent;
neither was selected. These development measurements do not establish how a
rejected candidate would perform on holdout.

The [first candidate](evidence/comparison-cpu-20260913/reflection-1/candidate.txt)
and [second candidate](evidence/comparison-cpu-20260913/reflection-2/candidate.txt)
copied illustrative name and issuer corrections from the development feedback,
despite instructions to avoid examples and document-specific values. This is
an instruction-following failure and a development-overfitting risk. Both were
eligible for evaluation under the frozen mechanical checks: a complete response,
the length limits and a nonduplicate prompt. The protocol did not include a
semantic check for copied examples. We retained the candidates and their measured
scores rather than introducing a new eligibility rule after seeing the outputs.

The second reflection received the first candidate and its development score;
it still produced a similar addendum with the same development score. The two
proposal calls used 3,376 prompt tokens and 254 completion tokens in total,
separately from the 18 calls evaluating their extraction behavior.

The [selection record](evidence/comparison-cpu-20260913/selection.json), frozen
at **2026-09-13 10:09:01 UTC**, retains the original direct prompt. Holdout had
not been generated or inspected during selection. Under the frozen protocol,
the rejected candidates receive no holdout evaluation; the selected method
reuses the original direct method's holdout run.

## Direct versus heuristic holdout errors

| Method | Clean OCR fields | Noisy OCR fields | Correct missing-field nulls | Exact documents |
| --- | ---: | ---: | ---: | ---: |
| [Heuristic](evidence/comparison-cpu-20260913/holdout-heuristic/metrics.json) | 76/76 | 69/76 | 12/12 | 17/24 |
| [Direct](evidence/comparison-cpu-20260913/holdout-direct/metrics.json) | 71/76 | 65/76 | 8/12 | 11/24 |

Five field errors are shared: damaged or displaced OCR dates and address text,
including `1977-0B-22`, `Val1eys` and a lost word boundary in `WilliamsMill`.
The canonicalizer does not repair these OCR substitutions or boundaries.

The [direct traces](evidence/comparison-cpu-20260913/holdout-direct/traces.jsonl)
show 11 additional field errors: four payer/payee swaps, two omitted visible
payer names, four incorrectly filled nulls, and one omitted visible bill date.
The swaps and payer omissions each repeat across a clean/noisy pair. For the
missing fields, direct substitutes a country or provider ZIP for the customer's
postal code, and an invoice ID for a blank transaction reference. These values
occur in the input: the error is assigning visible text to the wrong field,
not necessarily inventing characters. This explains errors even on clean OCR.

Direct also fixes two [heuristic errors](evidence/comparison-cpu-20260913/holdout-heuristic/traces.jsonl):
it restores `2025-O3-15` to a valid date and extracts a date from the reordered
line `2026-01-29PaymentDate`. The net difference is nine fewer correct fields
for direct. Both runs have valid outputs and no upstream truncation. These
observations concern 12 synthetic base documents and this model/configuration;
they do not establish a broader model ranking.

### Swarm's one-field gain

The [Swarm holdout report](evidence/comparison-cpu-20260913/holdout-swarm/metrics.json)
has one additional correct field and exact document: it recovers the visible
statement date `2025-03-29` that direct omitted in one noisy OCR variant.
There are no newly incorrect field positions. The payer/payee mistakes persist,
and correct missing-field nulls remain 8/12. One already incorrect postal code
changes from a country name to the provider ZIP; neither is the missing
customer value.

This costs 72 upstream requests versus 24 for direct, and 53,360 total tokens
versus 15,741, about 3.39 times as many. The observed mean document time is
32.92 seconds versus 16.47 seconds under the fixed-order, warm-cache setup.
One repaired field in one of 12 independent base documents is insufficient to
establish a reliable ensemble advantage.

### NER's role improvements and grounding limits

The [NER holdout report](evidence/comparison-cpu-20260913/holdout-ner/metrics.json)
has 71/76 correct clean-OCR fields and 68/76 noisy-OCR fields. It fixes all six
payer/payee and omitted-payer errors shared by direct and Swarm. However, its
[raw traces](evidence/comparison-cpu-20260913/holdout-ner/traces.jsonl) show that
grounding and role assignment solve different problems:

- In one clean/noisy pair, the model labels both the street and city as
  `ADDRESS_LINE1`. Conflict abstention removes the address, and `CITY` is absent:
  four incorrect fields across the pair.
- The model normalizes `2025-O3-15` into a valid date, but exact-source grounding
  removes it because the corrected characters do not occur in the OCR text.
- Two correct null references result from conflict abstention: the model labels
  both an invoice ID and an authorization code as the missing reference. In
  another pair, it returns just the authorization code, producing two wrong
  non-null references. A grounded value can still have the wrong role.
- One clean energy statement loses a visible issuer and statement date.

Thus the 10/12 correct nulls do not mean every absence was recognized correctly.
The service, role-specific prompts, source constraints and adapter policy are
evaluated together; this experiment does not isolate a generic NER architecture.

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
The runner uses [llama.cpp b10867](https://github.com/ggml-org/llama.cpp/releases/tag/b10867), commit f3f1a8f27, six CPU threads,
a 16,384-token context, one slot and no GPU layers. The executable, model,
service commits and exact command lines are recorded with each run.

The reported run used the official
[Ubuntu x64 archive](https://github.com/ggml-org/llama.cpp/releases/download/b10867/llama-b10867-bin-ubuntu-x64.tar.gz),
whose SHA-256 is
e52005c40754ad0608b633b699d63972e11f56deaa1c0f011881eaa491d84bb5.
Extract it with `tar --no-same-owner -xzf llama-b10867-bin-ubuntu-x64.tar.gz`
and retain the bundled libraries beside the executable.

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

### Re-score the saved evidence without a model

The [complete run](evidence/comparison-cpu-20260913) contains synthetic inputs,
separate gold, predictions, raw requests/responses and their checksums. The
[preflight evidence](evidence/comparison-preflight-cpu-20260913/preflight.json)
records the three exact toy-receipt results separately.

From the repository root, the following verifies retained file hashes and
recomputes every development and holdout report with the official scorer.
Temporary copies keep the original evidence unchanged:

~~~bash
uv run --frozen python - <<'PY'
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from rl_kyc_task_env.comparison import summarize_comparison

root = Path("docs/evidence/comparison-cpu-20260913")
for name, expected in json.loads((root / "sha256.json").read_text()).items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected, name
with tempfile.TemporaryDirectory() as work:
    for report in sorted(root.glob("*/metrics.json")):
        run = report.parent
        copy = Path(work) / run.name
        shutil.copytree(run, copy)
        split = run.name.split("-", 1)[0]
        actual = summarize_comparison(root / split, copy)
        assert actual == json.loads(report.read_text()), run.name
        print(run.name, actual["official_score"]["score"])
PY
~~~

The independent dataset and request audits are also included. Run them with
explicit paths and a fresh report filename:

~~~bash
uv run --frozen python docs/evidence/comparison-audit-cpu-20260913/verify_dataset.py \
  --repo . --evidence docs/evidence/comparison-cpu-20260913
uv run --frozen python docs/evidence/comparison-audit-cpu-20260913/verify_proxy.py \
  docs/evidence/comparison-cpu-20260913 --output /tmp/kyc-proxy-audit.json
~~~
