"""Real adversarial Docker integration; run explicitly (also required by CI).

KYC_DOCKER_TESTS=1 KYC_DOCKER_IMAGE=rl-kyc-eval:ci \
    python -m unittest discover -s tests -p test_isolation_docker.py -v

Skipping this module is not evidence that Docker isolation was verified.
"""
from __future__ import annotations

import json
import os
import shutil
import shlex
import subprocess
import tarfile
import tempfile
import unittest
import uuid
from pathlib import Path

from rl_kyc_task_env.containers import _run_container, run_hidden_judge, run_public_episode
from rl_kyc_task_env.bundles import build_public_bundle

ROOT = Path(__file__).resolve().parents[1]
IMAGE = os.environ.get("KYC_DOCKER_IMAGE", "rl-kyc-eval:ci")


@unittest.skipUnless(os.environ.get("KYC_DOCKER_TESTS") == "1", "Real Docker isolation gate requires KYC_DOCKER_TESTS=1")
class DockerIsolationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(["docker", "info"], check=True, capture_output=True)
        subprocess.run(["docker", "image", "inspect", IMAGE], check=True, capture_output=True)

    def make_bundle(self, root: Path, canary: str) -> Path:
        workspace = root / "bundle"
        doc_id = "doc_000000"
        document = workspace / "private/hidden_test" / doc_id
        shutil.copytree(ROOT / "private/hidden_test" / doc_id, document)
        gold_dir = workspace / "private/hidden_gold"
        gold_dir.mkdir(parents=True)
        shutil.copyfile(ROOT / "private/hidden_gold" / f"{doc_id}.json", gold_dir / f"{doc_id}.json")
        (gold_dir / "canary.txt").write_text(canary)
        (document / "target.json").write_text(canary)
        (document / "secret.py").write_text(canary)
        meta_path = document / "meta.json"
        meta = json.loads(meta_path.read_text())
        meta["hidden_seed"] = canary
        meta_path.write_text(json.dumps(meta))
        for component in ("judge", "rl_kyc_task_env", "task/schemas"):
            shutil.copytree(ROOT / component, workspace / component, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (workspace / "task/tools").mkdir()
        shutil.copyfile(ROOT / "task/tools/canonicalize.py", workspace / "task/tools/canonicalize.py")
        bundle = root / "private.tar.gz"
        with tarfile.open(bundle, "w:gz") as archive:
            for path in workspace.rglob("*"):
                if path.is_file():
                    archive.add(path, arcname=path.relative_to(workspace))
        return bundle

    def test_malicious_extractor_cannot_read_gold_or_poison_scorer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            canary = "GOLD-CANARY-" + uuid.uuid4().hex
            bundle = self.make_bundle(root, canary)
            solution = root / "solution"
            solution.mkdir()
            (solution / "extract.py").write_text('''
import json
import os
from pathlib import Path

# If scorer accidentally loads this module, its mounts expose private answers.
# Try obvious paths plus PID 1's namespace. The random secret is never in code.
def predict(document_dir):
    doc = Path(document_dir)
    forbidden = [
        Path('/workspace/private'), Path('/workspace/judge'),
        Path('/workspace/rl_kyc_task_env'), Path('/workspace/generator'),
        Path('/proc/1/root/workspace/private'),
        doc / 'target.json', doc / 'secret.py',
    ]
    accessible = [str(path) for path in forbidden if path.exists()]
    meta = json.loads((doc / 'meta.json').read_text())
    if 'hidden_seed' in meta:
        accessible.append(meta['hidden_seed'])
    # Persistent tampering in the first container must not reach the scorer.
    Path('/tmp/sitecustomize.py').write_text("raise RuntimeError('poisoned scorer')")
    for path in [Path('/workspace/private/hidden_gold/canary.txt'), Path('/proc/1/root/workspace/private/hidden_gold/canary.txt')]:
        try:
            accessible.append(path.read_text())
        except OSError:
            pass
    fields = {key: None for key in ['full_name','date_of_birth','document_number','issue_date','expiry_date','issuing_country']}
    fields['full_name'] = 'EXPOSED:' + repr(accessible) if accessible else 'ISOLATED'
    return {'schema_name': meta['schema_name'], 'fields': fields}
''')
            output = root / "output"
            result = run_hidden_judge(bundle, IMAGE, solution, output)
            predictions = json.loads((output / "predictions.json").read_text())
            self.assertEqual(predictions["documents"]["doc_000000"]["prediction"]["fields"]["full_name"], "ISOLATED")
            self.assertEqual(result["num_docs"], 1)
            self.assertEqual(result["score"], 0)
            self.assertNotIn(canary, (output / "predictions.json").read_text())
            manifest = json.loads((output / "judge_manifest.json").read_text())
            self.assertNotIn("/workspace/solution", manifest["container_policy"]["scorer_readonly_mounts"])

    def test_heuristic_works_with_minimal_collector_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = self.make_bundle(root, uuid.uuid4().hex)
            output = root / "output"
            result = run_hidden_judge(bundle, IMAGE, ROOT / "baselines/heuristic_baseline", output)
            predictions = json.loads((output / "predictions.json").read_text())
            self.assertEqual(predictions["documents"]["doc_000000"]["status"], "ok")
            self.assertGreater(result["score"], 0)

    def test_unprivileged_public_agent_edits_existing_seed_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed = root / "seed"
            (seed / "nested").mkdir(parents=True)
            (seed / "extract.py").write_text("def predict(_): return {}\n")
            (seed / "nested/helper.py").write_text("OLD = True\n")
            code = (
                "from pathlib import Path; p=Path('/workspace/solution'); "
                "(p/'extract.py').write_text('def predict(_): return {}\\n# edited\\n'); "
                "(p/'nested/helper.py').write_text('EDITED = True\\n'); "
                "(p/'nested/new.py').write_text('NEW = True\\n')"
            )
            output = root / "out"
            result = run_public_episode(
                build_public_bundle(root / "public.tar.gz"), IMAGE, output, seed,
                agent_command="python -c " + shlex.quote(code),
            )
            self.assertEqual(result["num_docs"], 90)
            self.assertIn("edited", (output / "solution/extract.py").read_text())
            self.assertEqual((output / "solution/nested/helper.py").read_text(), "EDITED = True\n")
            self.assertTrue((output / "solution/nested/new.py").exists())

    def test_timeout_kills_container_and_its_detached_processes(self):
        label = "kyc-timeout-probe-" + uuid.uuid4().hex
        result = _run_container(IMAGE, [], ["python", "-c", "import os,time; pid=os.fork(); os.setsid() if pid == 0 else None; time.sleep(120)", label], 2)
        self.assertEqual(result.returncode, 124)
        name = result.args[result.args.index("--name") + 1]
        existing = subprocess.run(["docker", "ps", "-a", "--filter", f"name=^{name}$", "--format", "{{.Names}}"], check=True, capture_output=True, text=True)
        self.assertEqual(existing.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
