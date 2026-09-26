# Phase 4, Stage 1 - Dependencies, CPU-only PyTorch, pgvector package

## What is being implemented

The five new dependencies Phase 4 needs (torch, transformers, sentence-transformers, pgvector, pillow, shap), with PyTorch specifically pinned to a CPU-only build via a dedicated `uv` index, plus a new `slow` pytest marker so tests that load real pretrained models stay out of the default fast test run. No feature/model code yet - this stage proves the (much heavier) environment can support Phase 4's work before building on top of it.

Files: `pyproject.toml`/`uv.lock` (new deps, `[tool.uv.sources]`/`[[tool.uv.index]]` for the CPU-only torch wheel index, `markers`/`addopts` for the `slow` marker).

## What it should look like

```
$ uv run python -c "import torch, transformers, sentence_transformers, pgvector, PIL, shap; print(torch.__version__, torch.cuda.is_available())"
2.14.0+cpu False
$ uv run pytest -q
90 passed in 22.51s
$ uv run slop smoke
[ok] Postgres reachable: ...
[ok] pgvector extension installed
[ok] MinIO put/get roundtrip in bucket 'thumbnails'
All smoke checks passed.
```

## What to look out for

- **The CPU-only PyTorch setup was verified for real, not assumed.** `torch` installed as `torch==2.14.0+cpu` - a 118.3MB download - instead of the multi-GB CUDA-bundled wheel PyPI serves by default on Windows, and `torch.cuda.is_available()` correctly prints `False`. This confirms the `[tool.uv.sources]`/`[[tool.uv.index]]` block pointing at `https://download.pytorch.org/whl/cpu` actually worked, not just that it was configured.
- **A real environment issue surfaced during this stage's verification, unrelated to the new dependencies**: Docker Desktop had stopped running at some point in this environment (the `com.docker.service` Windows service was stopped, and `docker compose ps` failed outright with "cannot find the Docker engine pipe"). Every test touching Postgres was hanging - not failing, hanging - because the connection attempt sat waiting on a port nothing was listening on instead of failing fast. This looked identical to a code-level regression from the new heavy dependencies at first glance; it wasn't. Diagnosed by running `pytest -v` with a hard external timeout to see exactly which test it got stuck on, then confirming via `docker compose ps` and `Get-Service com.docker.service`. Fixed by starting Docker Desktop and `docker compose up -d`. If you ever see the test suite hang (not just run slowly) after this stage, check Docker is actually running before suspecting the new ML libraries.
- The `slow` marker exists now but nothing uses it yet - no test currently loads a real model, so `uv run pytest` (which defaults to `-m 'not slow'`) and `uv run pytest -m slow` currently behave identically (both run all 90 existing tests, since none are marked). This starts mattering from Stage 3 onward.
- `shap`, `pillow`, and `pgvector` all installed as small, ordinary wheels - no surprises there. The only heavyweight items are `torch` (118MB CPU wheel) and `transformers`/`sentence-transformers` (11.7MB + their own transitive deps like `tokenizers`, `safetensors`, `huggingface-hub`).

## How to run tests properly

```powershell
# 0. Make sure Docker Desktop is actually running first (this bit me once already)
docker compose ps
docker compose up -d

uv run python -c "import torch, transformers, sentence_transformers, pgvector, PIL, shap; print(torch.__version__, torch.cuda.is_available())"
uv run pytest -q       # full existing suite - proves no import-time breakage
uv run slop smoke      # proves the app itself still boots correctly
```
