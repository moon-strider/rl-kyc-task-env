from __future__ import annotations

import json
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harness.diagnostics import load_json_output, write_json, write_summary

CONTAINER_CPUS = "2"
CONTAINER_MEMORY = "2g"
CONTAINER_PIDS_LIMIT = "256"
PUBLIC_AGENT_TIMEOUT_SECONDS = 900
PUBLIC_VALIDATOR_TIMEOUT_SECONDS = 300
HIDDEN_JUDGE_TIMEOUT_SECONDS = 300
_SKIP_NAMES = {"__pycache__", ".DS_Store"}
_SKIP_SUFFIXES = {".pyc", ".pyo"}


def _should_skip(path: Path) -> bool:
    return path.name in _SKIP_NAMES or path.suffix in _SKIP_SUFFIXES


def ensure_docker() -> None:
    subprocess.run(["docker", "info"], check=True, capture_output=True, text=True)


def build_eval_image(image: str, dockerfile: Path) -> str:
    ensure_docker()
    subprocess.run(
        ["docker", "build", "-f", str(dockerfile), "-t", image, "."],
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
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(bundle_path, "r:gz") as archive:
        archive.extractall(destination)
    return destination


def _copy_solution(source_dir: Path, destination_dir: Path) -> None:
    if _should_skip(source_dir):
        return
    if source_dir.is_file():
        destination_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_dir, destination_dir)
        return
    destination_dir.mkdir(parents=True, exist_ok=True)
    for path in source_dir.iterdir():
        _copy_solution(path, destination_dir / path.name)


def _run_container(
    image: str,
    mounts: list[tuple[Path, str, bool]],
    command: str,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    args = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--read-only",
        "--cpus",
        CONTAINER_CPUS,
        "--memory",
        CONTAINER_MEMORY,
        "--pids-limit",
        CONTAINER_PIDS_LIMIT,
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=256m",
        "--tmpfs",
        "/run:rw,noexec,nosuid,size=16m",
        "--workdir",
        "/workspace",
    ]
    for host_path, container_path, readonly in mounts:
        mount = f"type=bind,src={host_path},dst={container_path}"
        if readonly:
            mount += ",readonly"
        args.extend(["--mount", mount])
    args.extend([image, "/bin/sh", "-c", command])
    try:
        return subprocess.run(args, check=False, capture_output=True, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            args=args,
            returncode=124,
            stdout="",
            stderr=f"Container timeout after {timeout_seconds} seconds",
        )


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
        _copy_solution(seed_solution.resolve(), solution_dir)
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
        "python /workspace/task/tools/public_validator.py /workspace/solution",
        PUBLIC_VALIDATOR_TIMEOUT_SECONDS,
    )
    if validator_completed.returncode != 0:
        raise SystemExit(validator_completed.stderr or validator_completed.stdout or "Public validator failed")
    result = load_json_output(validator_completed.stdout)
    write_json(out_dir / "public_validator.json", result)
    write_summary(out_dir / "public_validator.txt", "public episode", result)
    shutil.copytree(solution_dir, out_dir / "solution", dirs_exist_ok=True)
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


def run_hidden_judge(
    bundle_path: Path,
    image: str,
    solution_dir: Path,
    output_dir: Path | None = None,
    keep_workspace: bool = False,
) -> dict[str, Any]:
    ensure_docker()
    out_dir = (output_dir or _default_output_dir("hidden_judges")).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    temp_root_ctx = tempfile.TemporaryDirectory(prefix="hidden-judge-")
    temp_root = Path(temp_root_ctx.name)
    workspace_root = temp_root / "workspace"
    extract_bundle(bundle_path.resolve(), workspace_root)
    staged_solution = temp_root / "solution"
    _copy_solution(solution_dir.resolve(), staged_solution)
    judge_completed = _run_container(
        image,
        [
            (workspace_root / "judge", "/workspace/judge", True),
            (workspace_root / "private", "/workspace/private", True),
            (workspace_root / "task", "/workspace/task", True),
            (workspace_root / "rl_kyc_task_env", "/workspace/rl_kyc_task_env", True),
            (staged_solution, "/workspace/solution", True),
        ],
        "python /workspace/judge/run_judge.py /workspace/solution",
        HIDDEN_JUDGE_TIMEOUT_SECONDS,
    )
    if judge_completed.returncode != 0:
        raise SystemExit(judge_completed.stderr or judge_completed.stdout or "Hidden judge failed")
    result = load_json_output(judge_completed.stdout)
    write_json(out_dir / "hidden_judge.json", result)
    write_summary(out_dir / "hidden_judge.txt", "hidden judge", result)
    manifest = {
        "kind": "hidden_judge",
        "bundle_path": str(bundle_path.resolve()),
        "image": read_image_metadata(image),
        "solution_dir": str(solution_dir.resolve()),
        "container_policy": {
            "network": "none",
            "read_only_rootfs": True,
            "cpus": CONTAINER_CPUS,
            "memory": CONTAINER_MEMORY,
            "pids_limit": CONTAINER_PIDS_LIMIT,
            "timeout_seconds": HIDDEN_JUDGE_TIMEOUT_SECONDS,
            "writable_mounts": ["/tmp", "/run"],
            "readonly_mounts": ["/workspace/judge", "/workspace/private", "/workspace/task", "/workspace/rl_kyc_task_env", "/workspace/solution"],
        },
    }
    write_json(out_dir / "judge_manifest.json", manifest)
    if keep_workspace:
        shutil.copytree(workspace_root, out_dir / "workspace", dirs_exist_ok=True)
    temp_root_ctx.cleanup()
    return result
