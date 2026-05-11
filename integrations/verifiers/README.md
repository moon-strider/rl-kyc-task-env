# Verifiers integration

This adapter exposes rl-kyc-task-env as a Verifiers single-turn environment.

The canonical benchmark remains the local evaluator. The adapter converts document records into Verifiers dataset rows and uses the same scoring code for rewards.

## Usage

```python
from rl_kyc_task_env.integrations.verifiers import load_environment

env = load_environment(split="train", limit=100)
```

Optional arguments:

- `split`: `train`, `val`, or `hidden_test`
- `limit`: maximum number of records
- `indices`: explicit document indices
- `schemas`: schema filter
- `mode`: currently only `single_turn`

## Dependency

`verifiers` is intentionally not a core dependency. Install it in your training environment when needed.

## Reward

The reward is the canonical document score in `[0, 1]`:

```text
0.9 * field_acc + 0.1 * exact_doc
```

The completion must contain JSON with `schema_name` and `fields`.
