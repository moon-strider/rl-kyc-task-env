# rl-kyc-task-env

Structured extraction from synthetic English-language identity documents, address statements, and payment receipts. Use it as a local benchmark or as the scoring environment for an agent-training experiment.

The package provides a shared reward function, public examples, isolated participant execution, and optional Verifiers/OpenReward adapters. A reproducible CPU model experiment is described in [docs/experiment.md](docs/experiment.md).

## Quickstart

Requires Python **3.12 or 3.13** and `uv` **0.12.11**. Docker is required for isolated execution.

```bash
git clone https://github.com/moon-strider/rl-kyc-task-env.git
cd rl-kyc-task-env
uv sync --frozen
uv run rl-kyc-public-validator baselines/heuristic_baseline
uv run python -m unittest discover -s tests
```

A participant supplies `extract.py` with this function:

```python
def predict(document_dir: str) -> dict:
    # Read meta.json, ocr.json, and optionally pages/0.png.
    return {"schema_name": "payment_receipt", "fields": {...}}
```

Use the fields from the matching schema in `task/schemas/`. Every required field must be present; values are strings or `null`, and extra keys are rejected.

The checked-in public heuristic score is **0.8468**. The null baseline scores **0**. These are synthetic benchmark results, not measured accuracy on real KYC documents.

## Install and use the package

```bash
uv build
uv run python scripts/check_install.py
```

The install check builds a wheel and source archive, installs the wheel into a clean environment outside the checkout, and exercises all four commands plus scoring on independent fixtures.

Datasets and gold answers are excluded from both distributions. Schemas, prompts, and runtime modules are included. If you install the wheel elsewhere, point it at a dataset checkout **before importing the package**:

```bash
export RL_KYC_DATA_ROOT=/absolute/path/to/rl-kyc-task-env
rl-kyc-public-validator /absolute/path/to/my-solution
```

The data root must contain `task/public_data/train`, `task/public_data/val`, and, when using hidden scoring, `private/hidden_test` and `private/hidden_gold`. A missing split raises an error explaining how to configure the data root.

The four installed commands are `rl-kyc-public-validator`, `rl-kyc-hidden-judge`, `rl-kyc-harness`, and `rl-kyc-experiment`; each supports `--help`.

## Safe evaluation of participant code

Run submitted code through the Docker harness:

```bash
uv run rl-kyc-harness build-public-bundle
uv run rl-kyc-harness build-private-judge-bundle --shard-name benchmark
uv run rl-kyc-harness build-eval-image --image rl-kyc-eval:local
uv run rl-kyc-harness run-public-episode --image rl-kyc-eval:local --seed-solution baselines/heuristic_baseline
uv run rl-kyc-harness run-hidden-judge --image rl-kyc-eval:local --solution-dir baselines/heuristic_baseline
```

Hidden evaluation uses two sequential containers:

1. The **collector** runs participant code with scrubbed document inputs and schema resources. Gold answers, the judge, and generation seeds are absent. It returns a bounded JSON prediction envelope.
2. The collector is removed. The **scorer** receives the frozen JSON and trusted gold; participant code is absent. It returns aggregate metrics.

Containers have no network, a read-only root filesystem, an unprivileged user, dropped capabilities, and limits on memory, processes, CPU, output, and elapsed time. Timeouts force container removal. Archive traversal, links, and special files are rejected. See [the isolation design](docs/isolation.md) for the boundary and its limits.

To score already collected predictions without executing code:

```bash
uv run rl-kyc-hidden-judge --predictions predictions.json
```

For a baseline you trust, local execution remains available:

```bash
uv run rl-kyc-hidden-judge --trusted-solution baselines/heuristic_baseline
```

Local Python execution, including the public validator, is for trusted code: it has access to the host filesystem. The explicit `--trusted-solution` option replaces the old positional hidden-judge command.

The repository publishes its example hidden dataset and seeds. Container isolation cannot prevent a participant from memorizing published answers. For a meaningful held-out evaluation, generate fresh data outside participant access and freeze predictions before revealing gold.

## Python API

```python
from rl_kyc_task_env import DocumentExtractionTask
from rl_kyc_task_env.prompts import build_document_prompt

task = DocumentExtractionTask(split="val", limit=1)
record = task.records[0]
observation = task.get_observation(record)
print(build_document_prompt(record))

# Evaluator-side sanity check: gold should score 1.0.
gold = task.load_document(record).gold
print(task.score_submission(record, gold).reward)
```

`get_observation` exposes metadata, schema, and OCR without returning gold. The task object itself belongs on the trusted evaluator side: `load_document` can read gold.

## Scoring and data

| Schema | Train | Validation | Example hidden |
| --- | ---: | ---: | ---: |
| `government_id` | 120 | 30 | 36 |
| `proof_of_address` | 120 | 30 | 36 |
| `payment_receipt` | 120 | 30 | 36 |

For each document, `score = 0.9 × field_accuracy + 0.1 × exact_document_match`. The final reward is the equal-weight mean of the three schema averages. Canonicalization handles casing, whitespace, dates, amounts, and supported currencies; it deliberately does not forgive OCR substitutions such as `O/0`.

The generator corrupts OCR tokens and geometry; the rendered page remains clean. OCR-only and image-enabled systems therefore receive different information and should be reported separately.

The checked-in hidden heuristic score is **0.8296**. The regenerated `benchmark` bundle has historically scored **0.8333**; use the actual run report when comparing changes.

## Model experiment

The `rl-kyc-experiment` command separates fresh dataset generation, model inference, development-only prompt reflection, and scoring of frozen predictions. It accepts an OpenAI-compatible local endpoint and requires no paid API when used with a local model.

[The experiment report](docs/experiment.md) records the model, prompts, seeds, hashes, OCR-only conditions, per-schema results, and limitations. This is an extraction and prompt-improvement experiment; it does not train model weights or establish an RL learning curve.

## Optional training adapters

```bash
uv sync --frozen --extra verifiers
uv sync --frozen --extra openreward
# Or both:
uv sync --frozen --extra frameworks
```

Adapters lazy-import their optional dependencies. See [Verifiers](integrations/verifiers/README.md) and [OpenReward](integrations/openreward/README.md) for their interfaces. Core installation and tests do not validate a full external training deployment.

## Verification

```bash
uv run python -m unittest discover -s tests
uv run python scripts/check_install.py
# Requires the built Docker image:
KYC_DOCKER_TESTS=1 KYC_DOCKER_IMAGE=rl-kyc-eval:local \
  uv run python -m unittest discover -s tests -p test_isolation_docker.py
```

GitHub Actions checks Python 3.12/3.13, clean wheel installation, bundle builds, real Docker isolation canaries, and public/hidden heuristic runs. Host unit tests alone do not establish Docker isolation. `just test` and `just check-install` are shortcuts; `just check` additionally regenerates the checked-in datasets.
