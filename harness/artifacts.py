from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from generator.generate_hidden import generate_hidden_dataset, load_hidden_seed
from generator.utils import HIDDEN_SEED, PUBLIC_SEED, REPO_ROOT
from harness.prompt_builder import write_agent_context

DIST_DIR = REPO_ROOT / "dist"
PUBLIC_BUNDLE_PATH = DIST_DIR / "public_bundle.tar.gz"
PRIVATE_BUNDLE_PATH = DIST_DIR / "private_judge_bundle.tar.gz"
_SKIP_NAMES = {"__pycache__", ".DS_Store"}
_SKIP_SUFFIXES = {".pyc", ".pyo"}


def _should_skip(path: Path) -> bool:
    return path.name in _SKIP_NAMES or path.suffix in _SKIP_SUFFIXES


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _copy_path(source: Path, destination: Path) -> None:
    if _should_skip(source):
        return
    if source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return
    if source.is_dir():
        destination.mkdir(parents=True, exist_ok=True)
        for child in source.iterdir():
            _copy_path(child, destination / child.name)
        return
    raise FileNotFoundError(source)


def _build_manifest(bundle_root: Path, bundle_type: str, extra: dict[str, Any]) -> dict[str, Any]:
    files = []
    for path in sorted(
        path
        for path in bundle_root.rglob("*")
        if path.is_file() and path.name != "manifest.json" and not _should_skip(path)
    ):
        files.append(
            {
                "path": path.relative_to(bundle_root).as_posix(),
                "size": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    return {
        "bundle_type": bundle_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": files,
        **extra,
    }


def _pack_bundle(bundle_root: Path, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output_path, "w:gz") as archive:
        for path in sorted(
            path for path in bundle_root.rglob("*") if path.is_file() and not _should_skip(path)
        ):
            archive.add(path, arcname=path.relative_to(bundle_root))
    return output_path


def build_public_bundle(output_path: Path | None = None) -> Path:
    output = output_path or PUBLIC_BUNDLE_PATH
    with tempfile.TemporaryDirectory(prefix="public-bundle-") as tmp_dir:
        bundle_root = Path(tmp_dir) / "bundle"
        bundle_root.mkdir(parents=True, exist_ok=True)
        _copy_path(REPO_ROOT / "task", bundle_root / "task")
        write_agent_context(bundle_root)
        manifest = _build_manifest(
            bundle_root,
            "public_bundle",
            {
                "public_seed": PUBLIC_SEED,
                "runtime_inputs": {
                    "dockerfile_sha256": _sha256_file(REPO_ROOT / "docker" / "eval-runtime.Dockerfile"),
                    "uv_lock_sha256": _sha256_file(REPO_ROOT / "uv.lock"),
                },
            },
        )
        _write_json(bundle_root / "manifest.json", manifest)
        return _pack_bundle(bundle_root, output)


def build_private_judge_bundle(output_path: Path | None = None, shard_name: str = "benchmark") -> Path:
    output = output_path or PRIVATE_BUNDLE_PATH
    with tempfile.TemporaryDirectory(prefix="private-bundle-") as tmp_dir:
        temp_root = Path(tmp_dir)
        bundle_root = temp_root / "bundle"
        bundle_root.mkdir(parents=True, exist_ok=True)
        private_root = bundle_root / "private"
        hidden_test_dir = private_root / "hidden_test"
        hidden_gold_dir = private_root / "hidden_gold"
        seed = load_hidden_seed(None, shard_name)
        generate_hidden_dataset(hidden_test_dir, hidden_gold_dir, seed)
        _copy_path(REPO_ROOT / "judge", bundle_root / "judge")
        _copy_path(REPO_ROOT / "task" / "schemas", bundle_root / "task" / "schemas")
        _copy_path(REPO_ROOT / "task" / "tools" / "canonicalize.py", bundle_root / "task" / "tools" / "canonicalize.py")
        _copy_path(REPO_ROOT / "task" / "tools" / "eval_core.py", bundle_root / "task" / "tools" / "eval_core.py")
        manifest = _build_manifest(
            bundle_root,
            "private_judge_bundle",
            {
                "shard_name": shard_name,
                "hidden_seed": seed,
                "benchmark_seed": HIDDEN_SEED,
                "runtime_inputs": {
                    "dockerfile_sha256": _sha256_file(REPO_ROOT / "docker" / "eval-runtime.Dockerfile"),
                    "uv_lock_sha256": _sha256_file(REPO_ROOT / "uv.lock"),
                    "seed_bank_sha256": _sha256_file(REPO_ROOT / "private" / "seed_bank.json"),
                },
            },
        )
        _write_json(bundle_root / "manifest.json", manifest)
        return _pack_bundle(bundle_root, output)
