set shell := ["/bin/zsh", "-cu"]

default:
    @just --list

sync:
    uv sync

generate-public:
    uv run python generator/generate_public.py

generate-hidden:
    uv run python generator/generate_hidden.py

generate-all:
    just generate-public
    just generate-hidden

validate-public solution="baselines/heuristic_baseline":
    uv run python task/tools/public_validator.py {{solution}}

judge-hidden solution="baselines/heuristic_baseline":
    uv run python judge/run_judge.py {{solution}}

validate-null:
    just validate-public baselines/null_baseline

validate-heuristic:
    just validate-public baselines/heuristic_baseline

judge-null:
    just judge-hidden baselines/null_baseline

judge-heuristic:
    just judge-hidden baselines/heuristic_baseline

check:
    just generate-all
    just validate-null
    just validate-heuristic
    just judge-null
    just judge-heuristic
