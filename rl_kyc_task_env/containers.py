from __future__ import annotations

import json
import os
import stat
import uuid
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from harness.diagnostics import load_json_output, write_json, write_summary
from .prediction_io import MAX_PREDICTION_FILE_BYTES, parse_prediction_envelope, write_prediction_file
from .runner import run_bounded_process

CONTAINER_CPUS = "2"
CONTAINER_MEMORY = "2g"
CONTAINER_PIDS_LIMIT = "256"
PUBLIC_AGENT_TIMEOUT_SECONDS = 900
PUBLIC_VALIDATOR_TIMEOUT_SECONDS = 300
HIDDEN_JUDGE_TIMEOUT_SECONDS = 900
MAX_SOLUTION_BYTES = 128 * 1024 * 1024
MAX_SOLUTION_ENTRIES = 10000
_SKIP_NAMES = {"__pycache__", ".DS_Store"}
_SKIP_SUFFIXES = {".pyc", ".pyo"}


def _should_skip(path: Path) -> bool:
    return path.name in _SKIP_NAMES or path.suffix in _SKIP_SUFFIXES


def ensure_docker() -> None:
    subprocess.run(["docker", "info"], check=True, capture_output=True, text=True)


def build_eval_image(image: str, dockerfile: Path) -> str:
    ensure_docker()
    subprocess.run(
        ["docker", "build", "-f", str(dockerfile), "-t", image, str(dockerfile.resolve().parents[1])],
        check=True,
    )
    return image


def read_image_metadata(image: str) -> dict[str, Any]:
    completed = subprocess.run(
        ["docker", "image", "inspect", image],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)[0]
    repo_digests = payload.get("RepoDigests") or []
    return {
        "image": image,
        "id": payload.get("Id"),
        "repo_digest": repo_digests[0] if repo_digests else None,
    }


def extract_bundle(bundle_path: Path, destination: Path) -> Path:
    """Extract regular files from a trusted bundle without following archive links."""
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with tarfile.open(bundle_path, "r:gz") as archive:
        members = archive.getmembers()
        if len(members) > 20000 or sum(member.size for member in members) > 512 * 1024 * 1024:
            raise ValueError("Bundle exceeds extraction limits")
        seen = set()
        for member in members:
            relative = PurePosixPath(member.name)
            if relative.is_absolute() or ".." in relative.parts or not relative.parts:
                raise ValueError("Unsafe bundle path")
            if not member.isfile() and not member.isdir():
                raise ValueError("Bundle links and special files are forbidden")
            target = root.joinpath(*relative.parts)
            if target in seen or not target.resolve().is_relative_to(root):
                raise ValueError("Duplicate or escaping bundle path")
            seen.add(target)
            if target.is_symlink():
                raise ValueError("Bundle destination contains symlink")
        for member in members:
            target = root.joinpath(*PurePosixPath(member.name).parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(0o644)
    return destination


def _copy_solution(source_dir: Path, destination_dir: Path, _budget: list[int] | None = None) -> None:
    """Copy regular files/directories only; never dereference solution symlinks."""
    if _should_skip(source_dir):
        return
    if _budget is None:
        _budget = [0, 0]  # entries and bytes across the whole staged tree
    _budget[0] += 1
    if _budget[0] > MAX_SOLUTION_ENTRIES:
        raise ValueError("Solution exceeds entry limit")
    mode = source_dir.lstat().st_mode
    if stat.S_ISREG(mode):
        destination_dir.parent.mkdir(parents=True, exist_ok=True)
        # O_NOFOLLOW closes the ordinary symlink-replacement window.
        descriptor = os.open(source_dir, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as source, destination_dir.open("wb") as output:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise ValueError("Solution contains a special file")
            if os.fstat(source.fileno()).st_size + _budget[1] > MAX_SOLUTION_BYTES:
                raise ValueError("Solution exceeds byte limit")
            while True:
                chunk = source.read(min(1024 * 1024, MAX_SOLUTION_BYTES - _budget[1] + 1))
                if not chunk:
                    break
                _budget[1] += len(chunk)
                if _budget[1] > MAX_SOLUTION_BYTES:
                    raise ValueError("Solution exceeds byte limit")
                output.write(chunk)
        destination_dir.chmod(0o755 if mode & 0o111 else 0o644)
        return
    if not stat.S_ISDIR(mode):
        raise ValueError("Solution links and special files are forbidden")
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination_dir.chmod(0o755)
    for path in source_dir.iterdir():
        _copy_solution(path, destination_dir / path.name, _budget)


def _make_solution_writable(solution_dir: Path) -> None:
    """Allow the unprivileged agent to edit its private staged seed tree."""
    solution_dir.chmod(0o777)
    for path in solution_dir.rglob("*"):
        mode = path.lstat().st_mode
        if stat.S_ISDIR(mode):
            path.chmod(0o777)
        elif stat.S_ISREG(mode):
            path.chmod(0o777 if mode & 0o111 else 0o666)
        else:
            raise ValueError("Staged solution contains link or special file")


def _run_container(
    image: str,
    mounts: list[tuple[Path, str, bool]],
    command: str | list[str],
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    name = "rl-kyc-" + uuid.uuid4().hex
    args = [
        "docker", "run", "--rm", "--name", name,
        "--network", "none", "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--user", "65534:65534",
        "--cpus", CONTAINER_CPUS, "--memory", CONTAINER_MEMORY,
        "--pids-limit", CONTAINER_PIDS_LIMIT,
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=256m,mode=1777",
        "--tmpfs", "/run:rw,noexec,nosuid,size=16m,mode=1777",
        "--workdir", "/workspace",
    ]
    for host_path, container_path, readonly in mounts:
        if "," in str(host_path) or "," in container_path:
            raise ValueError("Docker bind paths cannot contain commas")
        mount = f"type=bind,src={host_path},dst={container_path}"
        if readonly:
            mount += ",readonly"
        args.extend(["--mount", mount])
    # Shell is used only for the caller's explicitly requested agent command.
    # All harness-generated commands are argv; no host/user paths enter shell code.
    args.extend([image, *(["/bin/sh", "-c", command] if isinstance(command, str) else command)])
    try:
        return run_bounded_process(args, timeout_seconds, MAX_PREDICTION_FILE_BYTES)
    finally:
        # A timed-out Docker client does not stop the running container.
        # Never proceed to scoring if removal cannot be confirmed.
        cleanup = subprocess.run(["docker", "rm", "--force", name], capture_output=True, text=True, timeout=30)
        if cleanup.returncode != 0:
            if "No such container" not in cleanup.stderr:
                raise RuntimeError(f"Unable to remove evaluation container {name}")


def _default_output_dir(prefix: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path("dist") / prefix / stamp


def run_public_episode(
    bundle_path: Path,
    image: str,
    output_dir: Path | None = None,
    seed_solution: Path | None = None,
    agent_command: str | None = None,
    keep_workspace: bool = False,
) -> dict[str, Any]:
    ensure_docker()
    out_dir = (output_dir or _default_output_dir("public_episodes")).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    temp_root_ctx = tempfile.TemporaryDirectory(prefix="public-episode-")
    temp_root = Path(temp_root_ctx.name)
    workspace_root = temp_root / "workspace"
    extract_bundle(bundle_path.resolve(), workspace_root)
    task_dir = workspace_root / "task"
    solution_dir = temp_root / "solution"
    solution_dir.mkdir(parents=True, exist_ok=True)
    if seed_solution is not None:
        _copy_solution(seed_solution.absolute(), solution_dir)
    _make_solution_writable(solution_dir)
    agent_logs: dict[str, Any] | None = None
    if agent_command:
        agent_completed = _run_container(
            image,
            [
                (task_dir, "/workspace/task", True),
                (workspace_root / "rl_kyc_task_env", "/workspace/rl_kyc_task_env", True),
                (solution_dir, "/workspace/solution", False),
            ],
            agent_command,
            PUBLIC_AGENT_TIMEOUT_SECONDS,
        )
        agent_logs = {
            "returncode": agent_completed.returncode,
            "stdout": agent_completed.stdout,
            "stderr": agent_completed.stderr,
        }
        write_json(out_dir / "agent_logs.json", agent_logs)
        if agent_completed.returncode != 0:
            raise SystemExit(agent_completed.stderr or agent_completed.stdout or "Agent command failed")
    validator_completed = _run_container(
        image,
        [
            (task_dir, "/workspace/task", True),
            (workspace_root / "rl_kyc_task_env", "/workspace/rl_kyc_task_env", True),
            (solution_dir, "/workspace/solution", True),
        ],
        ["python", "/workspace/task/tools/public_validator.py", "/workspace/solution"],
        PUBLIC_VALIDATOR_TIMEOUT_SECONDS,
    )
    if validator_completed.returncode != 0:
        raise SystemExit(validator_completed.stderr or validator_completed.stdout or "Public validator failed")
    result = load_json_output(validator_completed.stdout)
    write_json(out_dir / "public_validator.json", result)
    write_summary(out_dir / "public_validator.txt", "public episode", result)
    _copy_solution(solution_dir, out_dir / "solution")
    manifest = {
        "kind": "public_episode",
        "bundle_path": str(bundle_path.resolve()),
        "image": read_image_metadata(image),
        "agent_command": agent_command,
        "seed_solution": str(seed_solution.resolve()) if seed_solution is not None else None,
        "container_policy": {
            "network": "none",
            "read_only_rootfs": True,
            "cpus": CONTAINER_CPUS,
            "memory": CONTAINER_MEMORY,
            "pids_limit": CONTAINER_PIDS_LIMIT,
            "timeout_seconds": {
                "agent": PUBLIC_AGENT_TIMEOUT_SECONDS,
                "validator": PUBLIC_VALIDATOR_TIMEOUT_SECONDS,
            },
            "writable_mounts": ["/workspace/solution", "/tmp", "/run"],
            "readonly_mounts": ["/workspace/task", "/workspace/rl_kyc_task_env"],
        },
    }
    write_json(out_dir / "episode_manifest.json", manifest)
    if keep_workspace:
        shutil.copytree(workspace_root, out_dir / "workspace", dirs_exist_ok=True)
    temp_root_ctx.cleanup()
    return result


def _stage_collector_inputs(workspace_root: Path, destination: Path) -> set[str]:
    """Expose document inputs and public schemas, never a private tree/package."""
    dataset_dir = workspace_root / "private" / "hidden_test"
    document_dirs = sorted(path for path in dataset_dir.iterdir() if path.is_dir())
    if not document_dirs:
        raise ValueError("Hidden dataset is empty")
    doc_ids = set()
    for document_dir in document_dirs:
        doc_ids.add(document_dir.name)
        target = destination / "documents" / document_dir.name
        target.mkdir(parents=True)
        meta = json.loads((document_dir / "meta.json").read_text())
        clean_meta = {key: meta[key] for key in ("doc_id", "schema_name", "num_pages", "language") if key in meta}
        write_json(target / "meta.json", clean_meta)
        _copy_solution(document_dir / "ocr.json", target / "ocr.json")
        pages = document_dir / "pages"
        for page in sorted(pages.glob("*.png")):
            _copy_solution(page, target / "pages" / page.name)
    _copy_solution(workspace_root / "task" / "schemas", destination / "task" / "schemas")
    # This public value normalizer is used by the supplied heuristic. It has no data.
    _copy_solution(workspace_root / "task" / "tools" / "canonicalize.py", destination / "task" / "tools" / "canonicalize.py")
    for filename in ("collector.py", "runner.py"):
        _copy_solution(Path(__file__).parent / filename, destination / "collector" / filename)
    return doc_ids


def run_hidden_judge(
    bundle_path: Path,
    image: str,
    solution_dir: Path,
    output_dir: Path | None = None,
    keep_workspace: bool = False,
) -> dict[str, Any]:
    """Collect inside a gold-free container, then score JSON in a fresh container.

    The image and private bundle are trusted infrastructure. Do not distribute
    private bundles or retained workspaces to participants. Use fresh held-out
    data for real evaluation: checked-in benchmark answers can be memorized.
    """
    ensure_docker()
    out_dir = (output_dir or _default_output_dir("hidden_judges")).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hidden-judge-") as tmp_dir:
        temp_root = Path(tmp_dir)
        workspace_root = temp_root / "workspace"
        extract_bundle(bundle_path.resolve(), workspace_root)
        staged_solution = temp_root / "solution"
        _copy_solution(solution_dir.absolute(), staged_solution)
        collector_root = temp_root / "collector-inputs"
        expected_doc_ids = _stage_collector_inputs(workspace_root, collector_root)
        collector_mounts = [
            (collector_root / "documents", "/workspace/documents", True),
            (collector_root / "task", "/workspace/task", True),
            (collector_root / "collector", "/workspace/collector", True),
            (staged_solution, "/workspace/solution", True),
        ]
        collected = _run_container(
            image, collector_mounts,
            ["python", "/workspace/collector/collector.py", "/workspace/solution", "/workspace/documents"],
            HIDDEN_JUDGE_TIMEOUT_SECONDS,
        )
        if collected.returncode != 0:
            raise RuntimeError(collected.stderr or "Hidden prediction collector failed")
        envelope = parse_prediction_envelope(collected.stdout, expected_doc_ids)
        # Create a fresh regular file from validated JSON. Never carry writable
        # filesystem state, links, modules or scripts out of the untrusted run.
        predictions_path = temp_root / "predictions.json"
        write_prediction_file(predictions_path, envelope)
        predictions_path.chmod(0o644)
        scorer_mounts = [
            (workspace_root / "judge", "/workspace/judge", True),
            (workspace_root / "private", "/workspace/private", True),
            (workspace_root / "task", "/workspace/task", True),
            (workspace_root / "rl_kyc_task_env", "/workspace/rl_kyc_task_env", True),
            (predictions_path, "/workspace/predictions.json", True),
        ]
        scored = _run_container(
            image, scorer_mounts,
            ["python", "/workspace/judge/run_judge.py", "--predictions", "/workspace/predictions.json"],
            HIDDEN_JUDGE_TIMEOUT_SECONDS,
        )
        if scored.returncode != 0:
            raise RuntimeError(scored.stderr or "Hidden prediction scorer failed")
        result = load_json_output(scored.stdout)
        write_prediction_file(out_dir / "predictions.json", envelope)
        write_json(out_dir / "hidden_judge.json", result)
        write_summary(out_dir / "hidden_judge.txt", "hidden judge", result)
        write_json(out_dir / "judge_manifest.json", {
            "kind": "hidden_judge", "bundle_path": str(bundle_path.resolve()),
            "image": read_image_metadata(image), "solution_dir": str(solution_dir.absolute()),
            "container_policy": {
                "network": "none", "read_only_rootfs": True, "user": "65534:65534",
                "cap_drop": "ALL", "no_new_privileges": True,
                "cpus": CONTAINER_CPUS, "memory": CONTAINER_MEMORY,
                "pids_limit": CONTAINER_PIDS_LIMIT,
                "timeout_seconds_per_phase": HIDDEN_JUDGE_TIMEOUT_SECONDS,
                "max_prediction_bytes": MAX_PREDICTION_FILE_BYTES,
                "collector_readonly_mounts": [target for _, target, _ in collector_mounts],
                "scorer_readonly_mounts": [target for _, target, _ in scorer_mounts],
                "writable_mounts": ["/tmp", "/run"],
            },
        })
        if keep_workspace:
            shutil.copytree(workspace_root, out_dir / "workspace")
        return result
