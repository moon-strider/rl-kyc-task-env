# rl-kyc-task-env

A framework-ready RL environment and local assessment benchmark for structured extraction from synthetic English-language KYC-style documents.

The repository is still usable as a simple local benchmark, but the implementation is now organized around an importable Python package, `rl_kyc_task_env`, with compatibility wrappers for the original public task, hidden judge, and Docker harness flows.

## What this is

The task asks an agent or participant solution to extract structured fields from single-page documents represented by:

- `meta.json`
- `ocr.json`
- `pages/0.png`

Supported schemas:

- `government_id`
- `proof_of_address`
- `payment_receipt`

Canonical participant contract:

```python
def predict(document_dir: str) -> dict:
    ...
```

The return value must be JSON-serializable and match the active schema:

```json
{
  "schema_name": "payment_receipt",
  "fields": {
    "sender_name": "..."
  }
}
```

## Quickstart

```bash
just sync
just check
```

Pinned runtime:

- Python `3.12.2`
- `uv` `0.7.7`

## Local evaluation

Public validation:

```bash
uv run python task/tools/public_validator.py baselines/heuristic_baseline
```

Hidden judging:

```bash
uv run python judge/run_judge.py baselines/heuristic_baseline
```

Expected baseline scores for checked-in datasets:

- public null: `0.0`
- public heuristic: `0.8468`
- hidden null: `0.0`
- hidden heuristic: `0.8296`

The isolated private judge bundle regenerates the benchmark hidden shard from the seed bank; its heuristic score is currently `0.8333`.

## Isolated execution

Production-style execution goes through bundles and containers:

```bash
just build-public-bundle
just build-private-judge-bundle
just build-eval-image
just run-public-episode
just run-hidden-judge
```

Public runtime mounts only the public task bundle and `/workspace/solution`. Hidden judging runs separately with the private judge bundle.

## Python package API

The package API is the canonical implementation surface for new code:

```python
from rl_kyc_task_env import DocumentExtractionTask

task = DocumentExtractionTask(split="val", limit=2)
record = task.records[0]
observation = task.get_observation(record)
result = task.score_submission(record, prediction)
print(result.reward)
```

Important modules:

- `rl_kyc_task_env.datasets`: split discovery and document records
- `rl_kyc_task_env.schemas`: schema loading and validation
- `rl_kyc_task_env.scoring`: canonical scoring and aggregation
- `rl_kyc_task_env.runner`: participant `extract.py` execution
- `rl_kyc_task_env.evaluation`: solution evaluation APIs
- `rl_kyc_task_env.bundles`: public/private bundle builders
- `rl_kyc_task_env.containers`: Docker runner APIs
- `rl_kyc_task_env.environment`: high-level environment API for integrations

Legacy entrypoints under `task/`, `judge/`, and `harness/` are compatibility wrappers over this package.

## Verifiers integration

The Verifiers adapter is optional and lazy-imported:

```python
from rl_kyc_task_env.integrations.verifiers import load_environment

env = load_environment(split="train", limit=100)
```

See `integrations/verifiers/README.md`.

`verifiers` is not a core dependency. Install it in the training environment only when needed.

## OpenReward / ORS integration

The OpenReward adapter exposes task listing, prompts, document tools, and canonical rewards:

```python
from rl_kyc_task_env.integrations.openreward import OpenRewardKycEnvironment

env = OpenRewardKycEnvironment(default_split="val", limit=10)
task = env.list_tasks("val")[0]
print(env.get_prompt(task))
print(env.submit_extraction(task, prediction))
```

See `integrations/openreward/README.md`.

`openreward` is not a core dependency. `build_server(...)` lazy-imports it and raises a clear error when it is absent.

## Scoring

For one document:

```text
field_acc = mean(exact_match(field_i))
exact_doc = 1 if all fields match else 0
doc_score = 0.9 * field_acc + 0.1 * exact_doc
```

For one schema:

```text
schema_score = mean(doc_score)
```

Final score:

```text
(government_id + proof_of_address + payment_receipt) / 3
```

The same scoring code is used by:

- public validation
- hidden judging
- package evaluation APIs
- Verifiers rewards
- OpenReward submission rewards

## Tests

Run all contract and integration smoke tests:

```bash
uv run python -m unittest discover -s tests
```

The tests freeze CLI compatibility, baseline scores, scoring behavior, bundle contents, environment APIs, and optional integration behavior.

## Development rules

- Keep dependency versions strictly pinned with `==`.
- Do not add optional framework dependencies to core runtime without explicit review.
- Preserve `extract.py -> predict(document_dir: str) -> dict` compatibility.
- Preserve score semantics unless intentionally changing benchmark rules.
