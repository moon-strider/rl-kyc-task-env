"""Standalone collector: deliberately imports no scoring/package/generator code.

The Docker harness mounts this file and runner.py alone. Every byte it outputs
is untrusted, including status fields. The host validates the bounded JSON.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from runner import run_prediction_subprocess


def main() -> int:
    solution_dir, dataset_dir = map(Path, sys.argv[1:])
    documents = {}
    for document_dir in sorted(dataset_dir.iterdir()):
        if not document_dir.is_dir():
            continue
        status, prediction = run_prediction_subprocess(solution_dir, document_dir)
        record = {"status": status}
        if status == "ok":
            record["prediction"] = prediction
        documents[document_dir.name] = record
    json.dump({"version": 1, "documents": documents}, sys.stdout, allow_nan=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
