#!/usr/bin/env bash
# Pinned official model and CPU runner. Downloads/builds outside the checkout.
set -euo pipefail

model_cache="${1:?Usage: bash scripts/local_model.sh /absolute/path/to/model-cache}"
mkdir -p "$model_cache"
model_cache="$(cd "$model_cache" && pwd)"
runner_revision=3057bb66c86c46d5781e50e85462a760ba7d1feb
model_revision=91cad51170dc346986eccefdc2dd33a9da36ead9
model_file=qwen2.5-1.5b-instruct-q4_k_m.gguf
model_sha=6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e

if [[ ! -d "$model_cache/llama.cpp/.git" ]]; then
    git init "$model_cache/llama.cpp"
    git -C "$model_cache/llama.cpp" remote add origin https://github.com/ggml-org/llama.cpp.git
    git -C "$model_cache/llama.cpp" fetch --depth 1 origin "$runner_revision"
    git -C "$model_cache/llama.cpp" checkout --detach FETCH_HEAD
fi
if [[ "$(git -C "$model_cache/llama.cpp" rev-parse HEAD)" != "$runner_revision" ]]; then
    echo 'Runner revision differs; use an empty model cache directory.' >&2
    exit 1
fi
python3 - "$model_cache/$model_file" "$model_revision" "$model_sha" <<'PY'
import hashlib
from pathlib import Path
import sys
from urllib.request import urlopen

path, revision, expected = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
if not path.exists():
    url = f"https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/{revision}/{path.name}"
    part = path.with_suffix(".part")
    with urlopen(url, timeout=180) as response, part.open("wb") as out:
        while chunk := response.read(8 * 1024 * 1024):
            out.write(chunk)
    part.rename(path)
with path.open("rb") as handle:
    actual = hashlib.file_digest(handle, "sha256").hexdigest()
if actual != expected:
    raise SystemExit(f"Model SHA-256 mismatch: {actual}; remove the invalid download and retry")
print(f"Verified official Qwen model: {actual}", flush=True)
PY
cmake -S "$model_cache/llama.cpp" -B "$model_cache/llama.cpp/build" \
    -DGGML_CUDA=OFF -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF \
    -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_TOOLS=ON -DCMAKE_BUILD_TYPE=Release
cmake --build "$model_cache/llama.cpp/build" --target llama-server -j "${KYC_BUILD_JOBS:-6}"
exec "$model_cache/llama.cpp/build/bin/llama-server" \
    --model "$model_cache/$model_file" --alias qwen2.5-1.5b-instruct \
    --host 127.0.0.1 --port "${KYC_MODEL_PORT:-8765}" \
    --ctx-size 16384 --threads "${KYC_MODEL_THREADS:-6}" --threads-batch "${KYC_MODEL_THREADS:-6}" \
    --parallel 1 --n-gpu-layers 0 --seed 17 --no-webui
