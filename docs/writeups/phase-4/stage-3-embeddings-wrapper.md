# Phase 4, Stage 3 - Shared sentence-embedding wrapper

## What is being implemented

`src/sloppy/features/embeddings.py` - a thin wrapper around `sentence-transformers`' `all-MiniLM-L6-v2` model (384-dim), loaded once per process via `@lru_cache` (mirroring `db/session.py`'s `get_engine()` pattern). `embed_texts(texts) -> np.ndarray` returns L2-normalized embeddings so cosine similarity downstream is a plain dot product. This is the shared building block Stages 4, 6, and 7 all consume.

## What it should look like

```python
>>> from sloppy.features.embeddings import embed_texts
>>> vecs = embed_texts(["hello world"])
>>> vecs.shape
(1, 384)
>>> import numpy as np; np.linalg.norm(vecs[0])
1.0000001  # unit norm, within floating-point tolerance
```

## What to look out for

- **This was actually verified against the real model, not just mocked** - I ran the `@pytest.mark.slow` test for real: it downloaded `sentence-transformers/all-MiniLM-L6-v2` (~90MB, first run only) and confirmed a real embedding comes back with shape `(1, 384)` and unit norm.
- **A real cold-start-import scare, worth understanding**: the first time `uv run pytest` imports anything that pulls in `sentence_transformers`/`transformers`, it can sit at "collecting..." for 30-90+ seconds before anything appears to happen. I initially treated this the same as the Docker-hang from Stage 1 and almost investigated it as a bug - it wasn't. It's a genuinely slow (not infinite) import, confirmed by waiting it out rather than assuming. This cost is paid once per fresh Python process (i.e., once per `pytest`/`slop` invocation), not once per test.
- **A harmless Windows-specific warning appears on first real model load**: `huggingface_hub` warns that it can't use symlinks for its cache on this machine (Windows without Developer Mode/admin), so cached model files get stored as full copies instead of symlinks - uses a bit more disk space, doesn't affect correctness. Nothing to fix; noted in `docs/writeups/TODO.md`.
- The fast test (`test_embed_texts_calls_model_with_normalize_and_numpy`) never touches the real model - it monkeypatches `_load_model` with a fake object, so it's instant and needs no download. Only the `@pytest.mark.slow` test is real.

## How to run tests properly

```powershell
# 1. Fast test (default suite - no model download, instant once modules are imported)
uv run pytest tests/test_features_embeddings.py -v
uv run pytest    # full suite - 95 passed, 1 deselected (the slow test)

# 2. Real-model verification (downloads ~90MB on first run, cached afterward)
uv run pytest tests/test_features_embeddings.py -m slow -v

uv run ruff check .
```
