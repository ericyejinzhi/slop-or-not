# Deviations from the Intended Schematic

Running log of places where the implementation diverges from [ROADMAP.md](ROADMAP.md),
with the reason and any follow-up needed. Add an entry whenever reality forces a change
the roadmap didn't anticipate.

## Phase 0 - Scaffolding (2026-09-17)

### MinIO image pulled from Quay, not Docker Hub

- **Intended**: `minio/minio:latest` from Docker Hub.
- **Actual**: `quay.io/minio/minio:latest` in `docker-compose.yml`.
- **Why**: the Docker Hub repository is no longer pullable ("pull access denied") - MinIO
  distributes its community images via Quay now.
- **Follow-up**: none; Quay is the canonical source.

### pgvector image fetched via Google's registry mirror (local workaround only)

- **Intended**: plain `docker compose pull` of `pgvector/pgvector:pg16` from Docker Hub.
- **Actual**: Docker Hub's CDN repeatedly dropped connections mid-layer from this network,
  so the image was pulled once via `mirror.gcr.io/pgvector/pgvector:pg16` and re-tagged
  locally as `pgvector/pgvector:pg16`.
- **Why**: persistent `httpReadSeeker ... EOF` failures from `production.cloudfront.docker.com`.
- **Follow-up**: `docker-compose.yml` is unchanged and still references the Docker Hub name.
  On another machine (or after `docker image rm`), a normal pull should work; if the CDN
  problem recurs, repeat: `docker pull mirror.gcr.io/pgvector/pgvector:pg16` then
  `docker tag mirror.gcr.io/pgvector/pgvector:pg16 pgvector/pgvector:pg16`.

### Python pinned to 3.12 despite system 3.14

- **Intended**: roadmap says Python 3.12 (matches).
- **Actual**: system Python is 3.14.3, so uv downloads and manages its own CPython 3.12.14
  (`.python-version`), and `pyproject.toml` pins `>=3.12,<3.13`.
- **Why**: 3.14 is too new for stable PyTorch / ML wheels needed from Phase 3–4 onward.
- **Follow-up**: revisit the upper pin once the ML stack publishes 3.13/3.14 wheels.

### Typer CLI needed an explicit callback

- **Intended**: `slop smoke` as a subcommand.
- **Actual**: added an empty `@app.callback()` in `src/sloppy/cli.py`.
- **Why**: Typer collapses a single-command app into the root command, which breaks
  `slop <subcommand>` syntax; the callback forces subcommand mode. Can be removed once a
  second real command exists (Phase 1's `slop ingest`), but it's harmless to keep.

### uv installed via winget

- **Intended**: roadmap assumed uv available.
- **Actual**: installed `astral-sh.uv` 0.12.15 via winget during Phase 0.
- **Follow-up**: only terminals opened after the install have `uv` on PATH.

## Phases 2-3 - first real-data run (2026-10-05)

### Train/val/test split is per-video, not grouped by channel

- **Intended**: ROADMAP.md Phase 2: "Stratified train/val/test split, grouped by channel -
  never let one channel's videos span train and test, or the model will just memorize
  channels."
- **Actual**: `slop label make-splits` defaults to `--group-by video` (label-stratified
  random split, ignoring channels). The channel-grouped split remains available as
  `--group-by channel`.
- **Why**: the project moved to channel-batch labeling (one judgment per channel), and the
  decision was that labeling should be per channel while training should not group by it.
- **Follow-up**: with channel-level labels, a by-video split leaks channel identity into
  the test set, so metrics are inflated (first real XGBoost run: PR-AUC about 0.98-0.99).
  Re-run training and evaluation with `--group-by channel` before quoting any number
  externally. See `docs/writeups/phase-3/real-data-first-run.md`.

### Sentiment scoring truncates comments at 512 tokens

- **Intended**: the roadmap does not mention it; the stage 5 implementation scored comments
  untruncated.
- **Actual**: `score_comments` passes `truncation=True, max_length=512`.
- **Why**: real comments over the RoBERTa limit crashed `compute-nlp`.
- **Follow-up**: none; only the first 512 tokens of a very long comment influence its score.
