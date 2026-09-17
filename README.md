# Slop-or-Not

YouTube content quality classifier using thumbnails, comments, channel sentiment, and
cross-video similarity. Full design and phased plan: [ROADMAP.md](ROADMAP.md).
Where implementation diverged from the plan and why: [DEVIATIONS.md](DEVIATIONS.md).

## Quickstart

```powershell
# 1. Copy env config (defaults work for local dev)
copy .env.example .env

# 2. Start Postgres (+pgvector) and MinIO
docker compose up -d

# 3. Install Python deps (installs Python 3.12 automatically if needed)
uv sync

# 4. Verify everything is wired up
uv run slop smoke

# 5. (once) install git hooks
uv run pre-commit install
```

MinIO console: http://localhost:9001 (credentials in `.env`).

## Development

```powershell
uv run pytest        # tests
uv run ruff check .  # lint
uv run ruff format . # format
uv run slop --help   # CLI
```
