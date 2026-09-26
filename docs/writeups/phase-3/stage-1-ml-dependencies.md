# Phase 3, Stage 1 - ML dependencies + config scaffolding

## What is being implemented

The five new dependencies Phase 3 needs (scikit-learn, xgboost, pandas, numpy, wandb) plus two new `Settings` fields for W&B. No feature/model code yet - this stage just proves the environment can actually support ML work before building on top of it.

Files: `pyproject.toml`/`uv.lock` (new deps), `src/sloppy/config.py` (add `wandb_api_key`, `wandb_project`), `.env`/`.env.example` (document the new optional vars).

## What it should look like

```
$ uv run python -c "import sklearn, xgboost, pandas, numpy, wandb; print('all imports ok')"
all imports ok
$ uv run slop smoke
[ok] Postgres reachable: ...
[ok] pgvector extension installed
[ok] MinIO put/get roundtrip in bucket 'thumbnails'
All smoke checks passed.
```

## What to look out for

- **This was genuinely a risk worth checking, not a formality** - `DEVIATIONS.md` records that Python was pinned to `>=3.12,<3.13` back in Phase 0 specifically because "3.14 is too new for stable PyTorch/ML wheels needed from Phase 3-4 onward," with a note to "revisit once the ML stack publishes 3.13/3.14 wheels." This is exactly that moment. Good news: all five packages installed cleanly as prebuilt wheels on Python 3.12 with no compilation, no `pip`/`uv` warnings, no version conflicts (versions resolved: scikit-learn 1.9.1, xgboost 3.4.1, pandas 3.0.6, numpy 2.5.3, wandb 0.30.0).
- **W&B is configured as best-effort/optional, per your explicit decision** - `wandb_api_key`/`wandb_project` are just settings fields here; nothing enforces their presence yet (that's Stage 7's `tracking.py`).
- CPU-only confirmed: nothing installed here pulls in CUDA, and none of the training code (Stage 7) sets a GPU device.

## How to run tests properly

```powershell
uv sync
uv run python -c "import sklearn, xgboost, pandas, numpy, wandb; print('all imports ok')"
uv run pytest      # full existing suite - proves no import-time breakage
uv run slop smoke  # proves the app itself still boots correctly
```
