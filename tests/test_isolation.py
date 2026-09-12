from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from rl_kyc_task_env.containers import _copy_solution, _make_solution_writable, _run_container, _stage_collector_inputs, extract_bundle
from rl_kyc_task_env.evaluation import evaluate_predictions
from rl_kyc_task_env.prediction_io import load_prediction_file, parse_prediction_envelope, write_prediction_file
from rl_kyc_task_env.runner import run_prediction_subprocess

ROOT = Path(__file__).resolve().parents[1]


class PredictionBoundaryTest(unittest.TestCase):
    def envelope(self, record=None):
        return {"version": 1, "documents": {"doc_000000": record or {"status": "ok", "prediction": {}}}}

    def test_malformed_envelopes_fail_closed(self):
        cases = [
            'null', '[]', '{"version":1,"version":1,"documents":{}}',
            json.dumps({"version": True, "documents": {}}),
            json.dumps(self.envelope({"status": "ok", "prediction": float("nan")})),
            json.dumps(self.envelope({"status": "ok", "prediction": "\ud800"})),
            '{"version":1,"documents":{"doc_000000":{"status":"ok","prediction":1e999}}}',
            json.dumps(self.envelope({"status": "ok", "prediction": {}, "score": 1})),
            json.dumps(self.envelope({"status": "timeout", "prediction": {}})),
            json.dumps({"version": 1, "documents": {"../gold": {"status": "timeout"}}}),
            json.dumps(self.envelope({"status": []})),
            json.dumps(self.envelope({"status": "ok", "prediction": "a" * 65536})),
            '{"version":1,"documents":{"doc_000000":{"status":"ok","prediction":' + '[' * 20 + '0' + ']' * 20 + '}}}',
        ]
        for payload in cases:
            with self.subTest(payload=payload[:80]), self.assertRaises(ValueError):
                parse_prediction_envelope(payload)
        with self.assertRaises(ValueError):
            parse_prediction_envelope(json.dumps(self.envelope()), {"other"})

    def test_valid_bounded_envelope_does_not_inflate_when_persisted(self):
        envelope = {"version": 1, "documents": {
            f"doc_{index:06}": {"status": "ok", "prediction": [0] * 21000}
            for index in range(100)
        }}
        validated = parse_prediction_envelope(json.dumps(envelope))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "predictions.json"
            write_prediction_file(path, validated)
            restored = load_prediction_file(path)
        self.assertEqual(len(restored["documents"]), 100)

    def test_symlink_and_fifo_prediction_inputs_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "predictions.json"
            target.write_text(json.dumps(self.envelope()))
            link = root / "link"
            link.symlink_to(target)
            with self.assertRaises(OSError):
                load_prediction_file(link)
            fifo = root / "fifo"
            os.mkfifo(fifo)
            with self.assertRaises(ValueError):
                load_prediction_file(fifo)

    def test_scoring_never_runs_participant_and_missing_counts_zero(self):
        doc = ROOT / "task/public_data/val/doc_000000"
        gold = json.loads((doc / "target.json").read_text())
        with patch("rl_kyc_task_env.evaluation.run_prediction_subprocess", side_effect=AssertionError("participant executed")):
            result = evaluate_predictions({doc.name: {"status": "ok", "prediction": gold}}, doc.parent, include_error_summary=True)
        self.assertEqual(result["num_docs"], 90)
        self.assertEqual(result["error_summary"], {"missing_prediction": 89})
        self.assertGreater(result["score"], 0)

    def test_empty_dataset_fails(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
            evaluate_predictions({}, Path(tmp))


class FilesystemBoundaryTest(unittest.TestCase):
    def test_tar_paths_links_and_special_files_rejected(self):
        cases = [("../outside", tarfile.REGTYPE), ("/absolute", tarfile.REGTYPE), ("link", tarfile.SYMTYPE), ("hard", tarfile.LNKTYPE), ("pipe", tarfile.FIFOTYPE)]
        for name, kind in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                archive = root / "bad.tar.gz"
                with tarfile.open(archive, "w:gz") as handle:
                    member = tarfile.TarInfo(name)
                    member.type = kind
                    member.linkname = "../outside"
                    if kind == tarfile.REGTYPE:
                        member.size = 1
                    handle.addfile(member, io.BytesIO(b"x") if kind == tarfile.REGTYPE else None)
                with self.assertRaises(ValueError):
                    extract_bundle(archive, root / "out")
                self.assertFalse((root / "outside").exists())

    def test_solution_symlinks_and_fifos_are_not_copied(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            (source / "extract.py").symlink_to(ROOT / "private/hidden_gold/doc_000000.json")
            with self.assertRaises(ValueError):
                _copy_solution(source, root / "out")
            (source / "extract.py").unlink()
            os.mkfifo(source / "fifo")
            with self.assertRaises(ValueError):
                _copy_solution(source, root / "out2")

    def test_staged_seed_tree_is_editable_by_container_user(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "nested").mkdir()
            (root / "nested/extract.py").write_text("pass\n")
            _make_solution_writable(root)
            self.assertEqual(root.stat().st_mode & 0o777, 0o777)
            self.assertEqual((root / "nested").stat().st_mode & 0o777, 0o777)
            self.assertEqual((root / "nested/extract.py").stat().st_mode & 0o777, 0o666)

    def test_solution_staging_bounds_entries_and_total_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            (source / "one.py").write_bytes(b"x" * 600)
            (source / "two.py").write_bytes(b"x" * 600)
            with patch("rl_kyc_task_env.containers.MAX_SOLUTION_BYTES", 1024):
                with self.assertRaisesRegex(ValueError, "byte limit"):
                    _copy_solution(source, root / "bytes-out")
            with patch("rl_kyc_task_env.containers.MAX_SOLUTION_ENTRIES", 2):
                with self.assertRaisesRegex(ValueError, "entry limit"):
                    _copy_solution(source, root / "entries-out")

    def test_collector_allowlist_drops_answers_and_private_metadata(self):
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            document = workspace / "private/hidden_test/doc_000000"
            shutil.copytree(ROOT / "task/public_data/val/doc_000000", document)
            # Public source includes target.json: it MUST NOT enter collector input.
            meta_path = document / "meta.json"
            meta = json.loads(meta_path.read_text())
            meta["hidden_seed"] = "CANARY-SEED"
            meta_path.write_text(json.dumps(meta))
            (document / "secret.py").write_text("CANARY-SOURCE")
            shutil.copytree(ROOT / "task/schemas", workspace / "task/schemas")
            (workspace / "task/tools").mkdir()
            shutil.copyfile(ROOT / "task/tools/canonicalize.py", workspace / "task/tools/canonicalize.py")
            staged = root / "staged"
            ids = _stage_collector_inputs(workspace, staged)
            self.assertEqual(ids, {"doc_000000"})
            files = {p.relative_to(staged).as_posix() for p in staged.rglob("*") if p.is_file()}
            self.assertNotIn("documents/doc_000000/target.json", files)
            self.assertNotIn("documents/doc_000000/secret.py", files)
            self.assertNotIn("hidden_seed", json.loads((staged / "documents/doc_000000/meta.json").read_text()))
            self.assertEqual({p.name for p in (staged / "collector").iterdir()}, {"collector.py", "runner.py"})
            self.assertFalse((staged / "rl_kyc_task_env").exists())


class ProcessBoundaryTest(unittest.TestCase):
    def test_prediction_timeout_and_output_flood_are_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            solution = Path(tmp)
            (solution / "extract.py").write_text("def predict(_):\n    while True: pass\n")
            start = time.monotonic()
            self.assertEqual(run_prediction_subprocess(solution, ROOT, 0.15)[0], "timeout")
            self.assertLess(time.monotonic() - start, 2)
            (solution / "extract.py").write_text("import os\ndef predict(_):\n    while True: os.write(1, b'x' * 65536)\n")
            self.assertEqual(run_prediction_subprocess(solution, ROOT, 1)[0], "output_limit")

    def test_forged_worker_status_is_a_document_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            solution = Path(tmp)
            for status in ([], {}, None):
                payload = json.dumps({"status": status}).encode()
                (solution / "extract.py").write_text(
                    f"import os\nos.write(1, {payload!r})\nos._exit(0)\n"
                )
                with self.subTest(status=status):
                    self.assertEqual(run_prediction_subprocess(solution, ROOT), ("runtime_exception", None))

    def test_successful_prediction_reaps_forked_children(self):
        with tempfile.TemporaryDirectory() as tmp:
            solution = Path(tmp)
            marker = solution / "escaped-child"
            (solution / "extract.py").write_text(
                "import os,time\ndef predict(_):\n"
                "    if os.fork() == 0:\n"
                "        os.close(1); os.close(2)\n"
                "        time.sleep(0.3)\n"
                f"        open({str(marker)!r}, 'w').write('alive')\n"
                "        os._exit(0)\n"
                "    return {}\n"
            )
            self.assertEqual(run_prediction_subprocess(solution, ROOT)[0], "ok")
            time.sleep(0.4)
            self.assertFalse(marker.exists())

    def test_timeout_removes_named_container(self):
        with patch("rl_kyc_task_env.containers.run_bounded_process", return_value=subprocess.CompletedProcess([], 124, "", "timeout")) as run, patch("rl_kyc_task_env.containers.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "", "")) as cleanup:
            result = _run_container("image", [], ["python", "script.py", "$(bad); value"], 1)
        self.assertEqual(result.returncode, 124)
        command = run.call_args.args[0]
        name = command[command.index("--name") + 1]
        self.assertEqual(cleanup.call_args.args[0], ["docker", "rm", "--force", name])
        self.assertEqual(command[-3:], ["python", "script.py", "$(bad); value"])
        self.assertNotIn("/bin/sh", command)
        self.assertIn("no-new-privileges", command)

    def test_cleanup_failure_prevents_scoring(self):
        with patch("rl_kyc_task_env.containers.run_bounded_process", return_value=subprocess.CompletedProcess([], 0, "{}", "")), patch("rl_kyc_task_env.containers.subprocess.run", return_value=subprocess.CompletedProcess([], 1, "", "daemon unavailable")):
            with self.assertRaisesRegex(RuntimeError, "Unable to remove"):
                _run_container("image", [], ["true"], 1)


if __name__ == "__main__":
    unittest.main()
