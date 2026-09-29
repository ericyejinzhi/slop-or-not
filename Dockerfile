# API-only image for the Phase 5 FastAPI service. Note: torch/transformers/
# sentence-transformers are full production dependencies (not dev-only), so this image
# is large (~2-3GB) even though the API itself doesn't call ML-model code directly yet -
# an accepted inefficiency for now (see docs/writeups/phase-5/stage-9-docker-compose.md),
# not solved in this phase.
FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --no-dev --frozen

EXPOSE 8000

# --no-sync: `uv run` re-syncs the environment against pyproject.toml on every
# invocation by default, which silently re-installs the dev group (ruff/pytest/httpx)
# the build-time `--no-dev` deliberately excluded - --no-sync uses the venv exactly as
# built, no re-sync, no network access needed at container start.
CMD ["uv", "run", "--no-sync", "uvicorn", "sloppy.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
