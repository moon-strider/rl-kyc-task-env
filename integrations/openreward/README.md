# OpenReward / ORS integration

This adapter exposes rl-kyc-task-env as an OpenReward-style environment surface.

The implementation keeps OpenReward optional. Core data access, task listing, prompt construction, document tools, and reward calculation work without installing OpenReward. `build_server(...)` lazy-imports `openreward` and raises a clear error when the package is absent.

## Environment surface

```python
from rl_kyc_task_env.integrations.openreward import OpenRewardKycEnvironment

env = OpenRewardKycEnvironment(default_split="val", limit=10)
task = env.list_tasks("val")[0]
print(env.get_prompt(task))
print(env.get_ocr(task))
print(env.submit_extraction(task, prediction))
```

## Tools

The adapter exposes the logical tools needed for ORS sessions:

- `get_metadata`
- `get_schema`
- `get_ocr`
- `get_page_image_info`
- `submit_extraction`

`submit_extraction` returns the canonical reward and marks the episode finished.

## Splits

- `train`
- `val`
- `hidden_test`

## Reward

Reward is exactly the canonical benchmark score in `[0, 1]`:

```text
0.9 * field_acc + 0.1 * exact_doc
```
