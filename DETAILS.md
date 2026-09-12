# Details

## Runtime

- Python `3.12` or `3.13`
- `uv` `0.12.11`
- Docker base image `python:3.12-slim`
- Docker runtime installs dependency lockfile with `uv sync --frozen --no-install-project`; task and package code are mounted from bundles during isolated runs

Direct dependencies:
- `Faker==40.13.0`
- `jsonschema==4.26.0`
- `numpy==2.4.4`
- `pandas==3.0.2`
- `Pillow==12.3.0`
- `pydantic==2.13.0`
- `python-dateutil==2.9.0.post0`
- `rapidfuzz==3.14.5`

The exact lockfile is `uv.lock`.

Optional framework extras:
- `verifiers`: `verifiers==0.1.11`
- `openreward`: `openreward==0.1.112`
- `frameworks`: both optional framework adapters

Packaging:
- build backend: `hatchling==1.29.0`
- `uv build` produces wheel and source distribution artifacts
- console scripts: `rl-kyc-public-validator`, `rl-kyc-hidden-judge`, `rl-kyc-harness`, `rl-kyc-experiment`
- framework dependencies are extras only and are lazy-imported by adapter modules
- wheel and sdist omit datasets and gold; runtime schemas and prompts are included
- set `RL_KYC_DATA_ROOT` before import to use data outside the runtime installation

## Repository Structure

- `rl_kyc_task_env/`: canonical importable package with datasets, schemas, scoring, runner, evaluation, bundle, container, environment, and integration APIs
- `task/`: public task interface, schemas, public data, normalization, and compatibility validation entrypoints
- `generator/`: data generation, rendering, OCR-noise pipeline, and templates
- `judge/`: hidden evaluation compatibility entrypoint
- `private/`: hidden documents, hidden gold, and private seed bank
- `baselines/`: `null_baseline` and `heuristic_baseline`
- `harness/`: compatibility artifact building, orchestration, diagnostics, and container runner entrypoints
- `integrations/`: human-facing documentation for optional framework integrations
- `docker/`: isolated runtime image

## Package Architecture

The package is the canonical implementation surface:

- `paths.py`: repository paths and split roots
- `records.py`: document, split, prediction, and submission result dataclasses
- `datasets.py`: split resolution, document discovery, metadata/OCR/gold loading
- `schemas.py`: schema loading, field names, and JSON Schema validation
- `prediction_io.py`: robust parsing helpers for adapter/model text outputs
- `scoring.py`: pure canonical scoring and aggregation
- `runner.py`: bounded participant subprocess execution with process-group cleanup
- `collector.py`: standalone prediction collection without gold or judge imports
- `experiments.py`: fresh fixtures, local endpoint inference, development reflection, and frozen-run scoring
- `evaluation.py`: solution/document evaluation APIs
- `bundles.py`: public/private bundle builders
- `containers.py`: Docker image and isolated runner APIs
- `prompts.py`: adapter-oriented prompt and OCR-line rendering
- `environment.py`: high-level environment API for rewards and observations
- `integrations/verifiers.py`: optional Verifiers adapter
- `integrations/openreward.py`: optional OpenReward/ORS adapter

Compatibility wrappers under `task/tools`, `judge`, and `harness` delegate to this package so existing CLI and Docker flows keep working.

## Data

Public splits:
- `train`: `360`
- `val`: `90`

Hidden split:
- `hidden_test`: `108`

Per schema:
- `government_id`: `120/30/36`
- `proof_of_address`: `120/30/36`
- `payment_receipt`: `120/30/36`

Each schema uses `6` templates:
- `4` public
- `2` hidden

## Document Format

Each document directory contains:
- `meta.json`
- `ocr.json`
- `pages/0.png`

Public `train` and `val` also contain:
- `target.json`

Hidden document directories in `hidden_test` do not contain `target.json`. Hidden gold is stored separately in `private/hidden_gold/`.

`meta.json` contains:
- `doc_id`
- `schema_name`
- `num_pages`
- `language`

`ocr.json` contains one page with:
- `width=1600`
- `height=2200`
- tokens with `text`, `bbox`, `line_id`, `block_id`, `conf`

## Output Contract

Every solution must return:

```json
{
  "schema_name": "<schema_name>",
  "fields": {
    "...": "..."
  }
}
```

Rules:
- top-level type is `object`
- `additionalProperties = false`
- required keys are `schema_name` and `fields`
- every field value is `string | null`

## Scoring

For one document:
- `field_acc = mean(exact_match(field_i))`
- `exact_doc = 1` if all fields match, otherwise `0`
- `doc_score = 0.9 * field_acc + 0.1 * exact_doc`

For one schema:
- `schema_score = mean(doc_score)`

Final score:

```text
(government_id + proof_of_address + payment_receipt) / 3
```

Public validation returns:
- `score`
- `by_schema`
- `num_docs`
- `error_summary`

Hidden judging returns only:
- `score`
- `by_schema`
- `num_docs`

## Normalization

`task/tools/canonicalize.py` applies:
- plain-text normalization via `NFKC`, trimming, space collapsing, and case-insensitive comparison
- date normalization to `YYYY-MM-DD`
- amount normalization to a decimal string with exactly two fractional digits
- currency normalization to `USD`, `EUR`, or `GBP`
- `document_number` and `reference_id` normalization through uppercase conversion and whitespace cleanup
- `postal_code` normalization through uppercase conversion and whitespace cleanup

OCR-confusion equivalence such as `O/0`, `I/1`, or `B/8` is intentionally not accepted during scoring.

## Data Generation

Public generation:
- `generator/generate_public.py`

Hidden generation:
- `generator/generate_hidden.py`

Supporting modules:
- `generator/field_sampling.py`
- `generator/render.py`
- `generator/ocr_noise.py`
- `generator/template_specs_public.py`
- `generator/template_specs_private.py`

Pipeline:
1. structured fields are sampled
2. a clean page is rendered
3. exact text boxes are recorded
4. lines are split into tokens
5. OCR-like corruption is applied to token text and geometry
6. corrupted tokens are written to `ocr.json`
7. `pages/0.png` remains clean

## Seeds

Fixed public seed:
- `PUBLIC_SEED = 20260413`

Fixed benchmark hidden seed:
- `HIDDEN_SEED = 90731157`

Rotating private hidden shards are described in `private/seed_bank.json`.

## Baseline Solutions

`baselines/null_baseline/extract.py`:
- returns the correct `schema_name`
- returns every field as `null`

`baselines/heuristic_baseline/extract.py`:
- reads `meta.json` and `ocr.json`
- reconstructs OCR lines
- uses label anchors and fuzzy matching for most fields
- handles the `proof_of_address` address block separately
- canonicalizes values before returning

## Isolated Container Execution

Public validation and hidden judging are intended to run through `harness`.

Build artifacts:

```bash
just build-public-bundle
just build-private-judge-bundle
just build-eval-image
```

Run a public episode:

```bash
just run-public-episode
```

Run hidden judging:

```bash
just run-hidden-judge
```

Direct CLI equivalents:

```bash
uv run python -m harness.cli.external_agent_eval build-public-bundle
uv run python -m harness.cli.external_agent_eval build-private-judge-bundle --shard-name benchmark
uv run python -m harness.cli.external_agent_eval build-eval-image --image rl-kyc-eval:local
uv run python -m harness.cli.external_agent_eval run-public-episode --image rl-kyc-eval:local --seed-solution baselines/heuristic_baseline
uv run python -m harness.cli.external_agent_eval run-hidden-judge --image rl-kyc-eval:local --solution-dir baselines/heuristic_baseline
```

Artifacts are written to `dist/`:
- `public_bundle.tar.gz`
- `private_judge_bundle.tar.gz`

## Isolation Model

The host, Docker daemon, runtime image, and dataset bundles are trusted organizer infrastructure. Participant code and every byte of its output are untrusted. Do not mount the repository root in a participant container.

The public repair loop can access the public task, including public targets, and its own solution. Hidden data is never mounted there.

Hidden execution has two separate stages:

1. A collector mounts only participant code, allowlisted metadata/OCR/page inputs, schemas, canonicalization, and a minimal collector/runner. It has no gold, private seeds, generator, judge, or full package source. Output is a bounded version-1 JSON envelope.
2. After confirmed collector removal, the trusted scorer receives that envelope, hidden gold, and trusted scoring code. No participant solution or writable participant directory is mounted in the scorer. Missing predictions count as zero; participant-supplied scores are rejected.

Both containers use no network, a read-only root, UID/GID 65534, dropped capabilities, `no-new-privileges`, and resource limits. Each Docker invocation has a unique name and is force-removed in `finally`, including client timeout. Local participant processes have wall-clock/output limits and process-group cleanup; detached sessions can outlive that local cleanup. Removing the whole collector container is the boundary that also removes detached processes. These controls reduce risk; Docker shares the host kernel and is not a VM boundary.

Private bundles and `keep_workspace` output are organizer-only artifacts and contain gold. The example hidden data and seed bank already published in this repository cannot serve as secret evaluation data. Generate fresh shards privately, keep them outside participant access, freeze predictions, and only then score them.

Local `evaluate_solution`, the public validator, and `--trusted-solution` execute code with host access. Use them only for owned/trusted baselines. `rl-kyc-hidden-judge --predictions FILE` evaluates a strictly parsed JSON file without executing participant code.

## Validation Status

Quick smoke check:

```bash
just check
```

Package and integration smoke tests:

```bash
uv run python -m unittest discover -s tests
```

Current checked-in dataset baseline results:
- public `null`: `0.0`
- public `heuristic`: `0.8468`
- hidden `null`: `0.0`
- hidden `heuristic`: `0.8296`

The isolated private judge bundle regenerates the benchmark hidden shard from the seed bank. Its current heuristic score is `0.8333`.

Verification gates now include:
- adversarial host tests for mount allowlists, archive traversal/links, strict envelopes, timeout/output limits, and cleanup
- real Docker canaries for hidden gold/seed access, process termination, and frozen scoring
- clean wheel installation outside the source checkout, including all console commands and external dataset scoring
- Python 3.12/3.13 CI and full public/hidden Docker smoke runs

Real Docker tests require `KYC_DOCKER_TESTS=1`. A skipped Docker test is not evidence of isolation. Consult the linked CI run and [experiment report](docs/experiment.md) for observed results rather than treating the design alone as verification.
