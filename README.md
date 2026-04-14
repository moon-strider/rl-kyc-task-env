# Document Extraction Assessment Environment

This repository contains a local assessment environment for structured data extraction from synthetic but realistic English-language documents.

It includes:
- a public task package for the participant or agent;
- a document generator for public and hidden datasets;
- a hidden judge;
- baseline solutions;
- an isolated containerized execution flow.

Supported document families:
- `government_id`
- `proof_of_address`
- `payment_receipt`

Pinned runtime:
- Python `3.12.2`
- `uv` `0.7.7`

## Quick Start

```bash
just sync
just check
```

## Isolated Execution

Production-style execution is expected to go through artifact building and containers:

```bash
just build-public-bundle
just build-private-judge-bundle
just build-eval-image
just run-public-episode
just run-hidden-judge
```

## Core Facts

- The participant contract is `extract.py` with `predict(document_dir: str) -> dict`.
- Public validation and hidden judging use the same normalization and the same scoring semantics.
- Hidden gold is stored separately from hidden document directories.
- Detailed architecture, data formats, isolation model, and execution flow are documented in `DETAILS.md`.
