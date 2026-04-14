from __future__ import annotations

import argparse
import json
from pathlib import Path

from harness.artifacts import (
    PRIVATE_BUNDLE_PATH,
    PUBLIC_BUNDLE_PATH,
    build_private_judge_bundle,
    build_public_bundle,
)
from harness.runner import build_eval_image, run_hidden_judge, run_public_episode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    public_bundle = subparsers.add_parser("build-public-bundle")
    public_bundle.add_argument("--output", default=str(PUBLIC_BUNDLE_PATH))

    private_bundle = subparsers.add_parser("build-private-judge-bundle")
    private_bundle.add_argument("--output", default=str(PRIVATE_BUNDLE_PATH))
    private_bundle.add_argument("--shard-name", default="benchmark")

    build_image = subparsers.add_parser("build-eval-image")
    build_image.add_argument("--image", default="rl-kyc-eval:local")
    build_image.add_argument("--dockerfile", default="docker/eval-runtime.Dockerfile")

    public_episode = subparsers.add_parser("run-public-episode")
    public_episode.add_argument("--bundle", default=str(PUBLIC_BUNDLE_PATH))
    public_episode.add_argument("--image", default="rl-kyc-eval:local")
    public_episode.add_argument("--output-dir", default=None)
    public_episode.add_argument("--seed-solution", default=None)
    public_episode.add_argument("--agent-command", default=None)
    public_episode.add_argument("--keep-workspace", action="store_true")

    hidden_judge = subparsers.add_parser("run-hidden-judge")
    hidden_judge.add_argument("--bundle", default=str(PRIVATE_BUNDLE_PATH))
    hidden_judge.add_argument("--image", default="rl-kyc-eval:local")
    hidden_judge.add_argument("--solution-dir", required=True)
    hidden_judge.add_argument("--output-dir", default=None)
    hidden_judge.add_argument("--keep-workspace", action="store_true")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "build-public-bundle":
        path = build_public_bundle(Path(args.output).resolve())
        print(path)
        return 0
    if args.command == "build-private-judge-bundle":
        path = build_private_judge_bundle(Path(args.output).resolve(), shard_name=args.shard_name)
        print(path)
        return 0
    if args.command == "build-eval-image":
        image = build_eval_image(args.image, Path(args.dockerfile).resolve())
        print(image)
        return 0
    if args.command == "run-public-episode":
        result = run_public_episode(
            Path(args.bundle).resolve(),
            args.image,
            output_dir=Path(args.output_dir).resolve() if args.output_dir else None,
            seed_solution=Path(args.seed_solution).resolve() if args.seed_solution else None,
            agent_command=args.agent_command,
            keep_workspace=args.keep_workspace,
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.command == "run-hidden-judge":
        result = run_hidden_judge(
            Path(args.bundle).resolve(),
            args.image,
            Path(args.solution_dir).resolve(),
            output_dir=Path(args.output_dir).resolve() if args.output_dir else None,
            keep_workspace=args.keep_workspace,
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
