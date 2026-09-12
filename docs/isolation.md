# Hidden evaluation boundary

`run_hidden_judge` uses two fresh containers. The evaluation image, bundle and
host are trusted. Participant code is allowed to run only in the collector.

1. The host extracts a private bundle, rejecting links, special files and path
   traversal. It copies the participant solution as regular files only, with
   limits of 10,000 filesystem entries and 128 MiB in total.
2. The collector receives document OCR and page PNGs, a small metadata allowlist,
   public schemas, the public canonicalizer, `collector.py`, `runner.py` and the
   solution. It receives **no gold directory, judge, package runtime, generator,
   seed bank, private manifest or private templates**. Unexpected document files
   such as `target.json` are excluded.
3. Each `predict(document_dir)` invocation runs in a separate subprocess. The
   collector emits JSON on stdout. This output is untrusted, including statuses.
   The entire collector container is removed before scoring starts.
4. The host validates the bounded versioned envelope and writes a new regular
   JSON file. Duplicate keys, unknown document IDs, nonfinite numbers, invalid
   Unicode, excessive nesting and unexpected record keys are rejected. Missing
   document records score zero. No writable files or Python modules are carried
   from the collector to the scorer.
5. A fresh scorer container receives the trusted runtime, documents, gold and the
   validated JSON file. It has **no participant solution mount** and calls
   `evaluate_predictions`, which never imports or executes participant code.

Both phases disable networking, run as UID/GID 65534, drop all Linux capabilities,
set `no-new-privileges` and use a read-only root filesystem and read-only bind
mounts. Only fresh `/tmp` and `/run` tmpfs mounts are writable. Limits are 2 CPUs,
2 GiB memory, 256 PIDs, 900 seconds per phase and 16 MiB combined process output.
Predictions are limited to 64 KiB per document and JSON nesting depth 16. The
individual prediction timeout is 5 seconds. Local cleanup kills the original
process group; a process that creates a detached session is stopped by removal
of the enclosing Docker container. A phase timeout forcibly removes that named
container; failed container cleanup
prevents scoring.

The scorer is not protected from an untrusted evaluation image or private bundle.
Checked-in hidden benchmark data and seeds are public research fixtures and can
be memorized. Use a fresh withheld shard to measure generalization; a gold-free
runtime does not make previously published answers secret.

## Frozen prediction format

```json
{
  "version": 1,
  "documents": {
    "doc_000000": {
      "status": "ok",
      "prediction": {
        "schema_name": "government_id",
        "fields": {}
      }
    },
    "doc_000001": {"status": "timeout"}
  }
}
```

The empty `fields` above illustrates the envelope only and is not a valid
prediction for the document schema. An `ok` record is subsequently checked
against that schema; invalid predictions receive zero. Error statuses are
`missing_extract`, `import_failure`, `runtime_exception`, `non_serializable`,
`timeout`, `output_limit`, `invalid_prediction` and `missing_prediction`.

Score a frozen file without executing participant code:

```bash
uv run python judge/run_judge.py --predictions predictions.json \
  --dataset-dir private/hidden_test --gold-dir private/hidden_gold
```

`evaluate_solution`, `evaluate_document`, `run_prediction_subprocess` and
`judge/run_judge.py --trusted-solution ...` execute code locally with access to
host files. They are conveniences for owned, trusted baselines and are **not
submission sandboxes**. The public validator is also a trusted local runner;
the public episode harness runs it inside Docker with public data only.

## Verification

`tests/test_isolation.py` checks filesystem staging, malicious archives, envelope
validation, scorer behavior, real subprocess timeouts/output limits and Docker
command cleanup. `tests/test_container_mounts.py` checks the two-phase mount
contract. These checks alone do not prove Docker isolation.

The separate integration gate executes a malicious solution against a randomly
generated gold canary, tries private paths and PID 1's filesystem, writes a
poisoned Python file to the first container's temporary filesystem, and verifies
that the canary cannot be returned and scoring still succeeds. It also verifies
the supplied heuristic with the minimal collector runtime and confirms that a
timeout removes a real container containing forked processes that created detached sessions.

```bash
docker build -f docker/eval-runtime.Dockerfile -t rl-kyc-eval:ci .
KYC_DOCKER_TESTS=1 KYC_DOCKER_IMAGE=rl-kyc-eval:ci \
  uv run python -m unittest discover -s tests -p test_isolation_docker.py -v
```

The integration tests skip when the environment flag is absent and fail if it is
set but Docker or the image is unavailable. CI runs this gate explicitly.
