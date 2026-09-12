"""Run the bounded OCR experiment against an already running local endpoint.

The holdout is generated only after the reflected candidate is frozen. This
script does not select another prompt using holdout results or train weights.
Run from an installed checkout: uv run python scripts/run_experiment.py OUTPUT.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, nullcontext
from pathlib import Path
from datetime import datetime, timezone
import subprocess
import time
from urllib.request import urlopen

from rl_kyc_task_env.experiments import DIRECT_PROMPT, generate, infer, reflect, sha256, summarize, write_json


@contextmanager
def local_server(runner: Path, model_file: Path, log: Path):
    """Keep server and client in one process tree (also works in isolated CI)."""
    with log.open("w") as handle:
        process = subprocess.Popen([
            str(runner.resolve()), "--model", str(model_file.resolve()),
            "--alias", "qwen2.5-1.5b-instruct", "--host", "127.0.0.1", "--port", "8765",
            "--ctx-size", "16384", "--threads", "6", "--threads-batch", "6",
            "--parallel", "1", "--n-gpu-layers", "0", "--seed", "17", "--no-webui",
        ], stdout=handle, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 60
            while True:
                if process.poll() is not None:
                    raise RuntimeError(f"Local server exited; see {log}")
                try:
                    with urlopen("http://127.0.0.1:8765/health", timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    pass
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Local server did not become ready; see {log}")
                time.sleep(0.25)
            yield
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8765/v1/chat/completions")
    parser.add_argument("--model", default="qwen2.5-1.5b-instruct")
    parser.add_argument("--runner", type=Path, help="Optional local llama-server executable")
    parser.add_argument("--model-file", type=Path, help="GGUF model when --runner is supplied")
    parser.add_argument("--exploratory-prompt", type=Path,
                        help="Optional prewritten dev-guided prompt; kept separate from automatic reflection")
    args = parser.parse_args()
    root = args.output
    if root.exists():
        parser.error("Use a new output directory; existing evidence is never overwritten")
    if bool(args.runner) != bool(args.model_file):
        parser.error("--runner and --model-file must be supplied together")
    if args.runner and args.endpoint != "http://127.0.0.1:8765/v1/chat/completions":
        parser.error("--runner uses the default local endpoint")
    root.mkdir(parents=True)
    context = local_server(args.runner, args.model_file, root / "server.log") if args.runner else nullcontext()
    with context:
        run_experiment(args)


def run_experiment(args: argparse.Namespace) -> None:
    root = args.output
    dev = root / "dev"
    generate(dev, 2026091201, 3, "dev")

    def run(split: Path, name: str, method: str, prompt: str) -> None:
        directory = root / name
        infer(split / "inputs", directory, method, prompt, args.endpoint, args.model, 512, 180, None)
        summarize(split, directory)

    run(dev, "dev-heuristic", "heuristic", DIRECT_PROMPT)
    run(dev, "dev-direct", "llm", DIRECT_PROMPT)
    reflect(dev, root / "dev-direct", root / "reflection", args.endpoint, args.model, 768, 180, None)
    candidate = (root / "reflection" / "candidate.txt").read_text().strip()
    run(dev, "dev-reflected", "llm", candidate)
    exploratory = None
    if args.exploratory_prompt:
        exploratory = args.exploratory_prompt.read_text().strip()
        (root / "dev-guided-prompt.txt").write_text(exploratory + "\n")
        write_json(root / "dev-guided-freeze.json", {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "method": "replay of separately supplied analyst-written exploratory prompt",
            "prompt_sha256": sha256(root / "dev-guided-prompt.txt"),
            "holdout_generated": False, "holdout_outputs_inspected": False,
        })
        run(dev, "dev-guided", "llm", exploratory)
    write_json(root / "freeze.json", {
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "direct_prompt_sha256": sha256(root / "dev-direct" / "prompt.txt"),
        "candidate_sha256": sha256(root / "reflection" / "candidate.txt"),
        "selection_rule": "Evaluate direct and the single reflected candidate; no holdout-driven selection",
        "holdout_generated": False,
    })
    holdout = root / "holdout"
    generate(holdout, 2026091202, 4, "holdout")
    run(holdout, "holdout-heuristic", "heuristic", DIRECT_PROMPT)
    run(holdout, "holdout-direct", "llm", DIRECT_PROMPT)
    run(holdout, "holdout-reflected", "llm", candidate)
    if exploratory is not None:
        run(holdout, "holdout-guided", "llm", exploratory)


if __name__ == "__main__":
    main()
