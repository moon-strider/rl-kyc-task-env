# Validation record — 2026-09-12

## Local checks

| Check | Observed result |
| --- | --- |
| `uv run --frozen python -m unittest discover -s tests` | 79 tests: 75 passed, 4 explicitly skipped Docker integration tests; 52.247 s |
| Existing public/hidden baseline contracts | Null 0; public heuristic 0.8468; checked-in hidden heuristic 0.8296 |
| `uv run python scripts/check_install.py` | Clean installed wheel outside checkout; four CLI entrypoints; three bundled schemas; external fixture data; public null 0 and frozen hidden predictions 1 |
| `uv lock --check` | Passed |
| README package API example | Passed: observation, real prompt helper, evaluator gold sanity score 1 |
| Final experiment diagnostics | 21 focused tests passed; saved reflected predictions also scored successfully through the installed hidden-judge CLI (0.6452) |
| `pip-audit` against the core environment | 17 external distributions, no known vulnerabilities after Pillow 12.3.0 update; local project excluded from registry lookup |

The complete dependency report is [dependency-audit.json](evidence/dependency-audit.json). Optional framework extras were not installed or audited in this run.

Adversarial tests cover bundle traversal/links/special files, limited submission copying, exclusion of hidden answers and generator inputs, strict prediction parsing, malformed worker status values, output expansion during persistence, timeout/output-flood handling, and cleanup calls. Frozen predictions are scored without importing participant code. Local process-group cleanup does not contain intentionally detached sessions; submitted code must use the Docker path.

## Docker and Python matrix

Python 3.12/3.13 contracts and clean installs, bundle builds, and all four real Docker isolation tests passed in [GitHub Actions](https://github.com/moon-strider/rl-kyc-task-env/actions/runs/34702938809). Its required gates are Python 3.12/3.13 contracts and clean wheel installation, bundle builds, and real Docker integration plus full public/hidden heuristic runs.

The four Docker tests exercise a random hidden-gold canary and scorer poisoning attempt, a working heuristic in the minimal collector, removal of a timed-out container with a detached child, and modification of seeded nested solution files by the unprivileged public agent. Docker was unavailable locally; skipped local tests are not evidence of container isolation. The entire linked CI run passed, including all four Docker isolation tests and the complete public and hidden heuristic runs.

## Real model experiment

[docs/experiment.md](experiment.md) documents actual Qwen CPU inference, all raw predictions, and negative automatic-reflection results. API credentials were unnecessary. The saved synthetic holdout is now public, so future private evaluations must generate fresh data. This experiment does not train weights or establish an RL improvement curve.
