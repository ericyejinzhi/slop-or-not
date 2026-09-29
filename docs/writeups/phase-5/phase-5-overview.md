# Phase 5 - FastAPI service (full write-up)

This covers the whole of Phase 5 end-to-end. For stage-by-stage detail, see `stage-1-fastapi-skeleton.md` through `stage-9-docker-compose.md` in this same directory.

## What is being implemented

The first phase to expose any of this project's work outside a CLI context: a FastAPI service serving `GET /videos` (paginated, filterable, sortable, with scores and presigned thumbnail URLs), `GET /videos/{id}` (full metadata + NLP/vision feature breakdown + similar videos by CLIP thumbnail similarity), `POST /ingest` (schedules a channel or single-video ingest via `BackgroundTasks`), and `POST /labels` (records a label). This will become Phase 6's React dashboard's entire backend.

Built across nine stages:

1. **App skeleton** (`src/sloppy/api/app.py`) - `create_app()` factory, `GET /health`, `fastapi`/`uvicorn`/`httpx` added as dependencies.
2. **Single-video ingest** (`src/sloppy/ingest/pipeline.py::ingest_video`) - fills a real gap: only whole-channel ingestion existed publicly before this.
3. **Nearest-neighbor thumbnail similarity** (`src/sloppy/features/similarity.py::nearest_videos_by_thumbnail`) - the ranked-list counterpart to Phase 4's aggregate-only similarity functions.
4. **Presigned thumbnail URLs** (`src/sloppy/storage.py::generate_presigned_url`) - the first way to hand a browser a directly-loadable thumbnail URL.
5. **Pydantic schemas + `videos` router** (`src/sloppy/api/schemas.py`, `src/sloppy/api/routers/videos.py`) - the core read path; also where `Settings.active_model_name`/`active_model_version` were actually added (needed here functionally, ahead of their originally-planned Stage 8).
6. **`ingest` and `labels` routers** (`src/sloppy/api/routers/{ingest,labels}.py`) - the two write endpoints.
7. **Centralized error handling** (`src/sloppy/api/errors.py`) - `ValueError` -> 404, `IntegrityError` -> 409, both currently defense-in-depth given the API's explicit checks elsewhere.
8. **Active-model config test + TODO.md** - documentation and testing for the fields added in Stage 5.
9. **Docker-compose `api` service + Dockerfile** - the first `Dockerfile` in this project, plus the phase overview you're reading now.

## Architecture, end to end

```
Client (curl / future React dashboard)
        |
        v
FastAPI app (src/sloppy/api/app.py::create_app())
        |
        +--- GET /videos, GET /videos/{id}  (routers/videos.py)
        |       |
        |       +--> Depends(get_db) -> session_scope() -> real Postgres query
        |       |     (Video + Channel join, outerjoin VideoScore on resolved
        |       |      active_model_name/version, VideoNlpFeatures/VideoVisionFeatures
        |       |      by PK, nearest_videos_by_thumbnail() raw pgvector <=> query)
        |       +--> Depends(get_s3) -> generate_presigned_url() per thumbnail
        |       +--> Pydantic response schemas (schemas.py)
        |
        +--- POST /ingest  (routers/ingest.py)
        |       +--> BackgroundTasks.add_task(ingest_channel | ingest_video, settings, target)
        |       +--> 202 Accepted, returned immediately - no job tracking
        |
        +--- POST /labels  (routers/labels.py)
        |       +--> explicit Video-exists check -> record_label() -> 201 Created
        |
        +--- errors.py: ValueError -> 404, IntegrityError -> 409 (registered globally)

docker-compose.yml: api service (new Dockerfile) + postgres + minio
  - dev workflow: `uv run uvicorn --reload` on the host, against published ports
  - container: POSTGRES_HOST=postgres, S3_ENDPOINT_URL=http://minio:9000 overrides
```

Every router follows the conventions established in Phases 1-4: `session_scope()` for DB access (via a `get_db` FastAPI dependency instead of a bare `with` block, since this is the first non-CLI consumer), no ORM `relationship()` (every join is manual `select()`/raw SQL), one test file per module, `_cleanup()`-guarded live-Postgres/MinIO integration tests via `TestClient` instead of mocking.

## What it should look like

Once real ingested/labeled data and a trained model exist:

```
$ curl "http://localhost:8000/videos?limit=5"
{"items": [{"id": "...", "title": "...", "score": 0.73, "predicted_label": "down",
            "thumbnail_url": "http://localhost:9000/thumbnails/....jpg?X-Amz-...", ...}],
 "total": 412, "limit": 5, "offset": 0}

$ curl "http://localhost:8000/videos/<id>"
{"id": "...", "score": 0.73, "nlp_features": {...}, "vision_features": {...},
 "similar_videos": [{"video_id": "...", "distance": 0.04, ...}, ...]}

$ curl -X POST http://localhost:8000/ingest -d '{"video_id": "abc123"}'
{"status": "accepted", "target": "abc123"}   # 202, immediately

$ curl -X POST http://localhost:8000/labels -d '{"video_id": "abc123", "labeler": "alice", "label": "down"}'
{"video_id": "abc123", "labeler": "alice", "label": "down", "notes": null, "created_at": "..."}
```

`/docs` renders Swagger UI with all 4 endpoints, their query/body schemas, and response models fully documented from the Pydantic types - confirmed by manual inspection in every stage.

## What to look out for

**One real bug was found and fixed during implementation** (Stage 9): the Dockerfile's `CMD ["uv", "run", "uvicorn", ...]` looked correct but caused `uv run` to silently re-sync the environment (re-installing the dev dependency group - `ruff`, `pytest`, `httpx`) on every container start, defeating the build-time `uv sync --no-dev`'s intent. Fixed with `uv run --no-sync uvicorn ...`. Confirmed via a real `docker compose up --build api` + `curl` run: the fix eliminated the re-sync noise, and the container still started cleanly and responded correctly.

**The single most important thing to remember going into Phase 6**: presigned thumbnail URLs bake in whatever `S3_ENDPOINT_URL` the generating process was configured with. Running the API via `uv run uvicorn` on the host (the normal dev workflow throughout this phase) produces browser-usable URLs (`http://localhost:9000/...`). Running it via `docker compose up api` produces URLs pointing at `http://minio:9000` - unreachable from a host browser. This is flagged repeatedly (Stages 4 and 9) as a known, accepted gap - not solved in this phase, and something Phase 6's dashboard development should be aware of (develop against the host-run API, not the containerized one, until this is addressed).

**Design decisions worth remembering**:
- `POST /ingest` is fire-and-forget (`BackgroundTasks`, no job-id/status tracking) - real orchestration is explicitly Phase 7's job, not rebuilt here.
- An unresolved active model (`Settings.active_model_name`/`version` both blank, and no query-param override) makes every score/predicted_label `null` rather than erroring - a join that matches nothing, not a branch in the query logic.
- `GET /videos/{id}`'s "similar videos" is CLIP-thumbnail-only (not title embeddings, not a blend) - a confirmed, deliberate scope decision.
- Both centralized exception handlers (`ValueError` -> 404, `IntegrityError` -> 409) are currently defense-in-depth, not load-bearing for any endpoint that exists today - every "not found" and "invalid input" case in the current API is caught by an explicit check or Pydantic validation before either handler would ever fire. Worth re-verifying end to end if a future endpoint changes that.
- No authentication or rate limiting was built - correctly out of scope per the roadmap for every phase before Phase 8.

**No real ingested/labeled data exists yet anywhere in this environment** - every stage was still verified for real, not just unit-tested in isolation: Stages 2, 3, 6 (ingest) are fully offline/monkeypatched integration tests against the real dev Postgres; Stage 4's presigned-URL test genuinely fetches a real MinIO-hosted object via plain `httpx`; Stage 5's 7 endpoint tests hit real Postgres + MinIO through `TestClient` with fixture rows inserted via the real upsert helpers, and passed on the first run; Stage 9's Docker smoke test was actually run, not just described.

## How to run tests properly

```powershell
# 1. Bring up the dev stack
docker compose up -d postgres minio

# 2. Full automated suite - 154 passed, 5 deselected as of the end of Phase 5
uv run pytest

# 3. Lint + format
uv run ruff check .
uv run ruff format --check .

# 4. Manual API check (no real data needed to confirm wiring)
uv run uvicorn sloppy.api.app:app --reload --port 8000
curl http://localhost:8000/health
curl http://localhost:8000/videos
# open http://localhost:8000/docs in a browser

# 5. Docker container smoke test
docker compose up --build api
curl http://localhost:8000/health
docker compose ps
docker compose stop api

# 6. The pieces that need real data (see docs/writeups/TODO.md for the full list):
#    a. Finish Phases 1-4 for real (ingest, label, compute-nlp/compute-vision, train a model)
#    b. Set ACTIVE_MODEL_NAME/ACTIVE_MODEL_VERSION in .env (TODO.md item 15)
#    c. uv run slop ingest / label / features / model commands, then hit the API for real
```

## What's next

Phase 5's code is complete; the remaining work is entirely about real data (still blocked on Phase 2's curation/labeling, per `docs/writeups/TODO.md`) and, once a model exists, promoting it to active. Per `ROADMAP.md`, Phase 6 ("React dashboard") is next: Vite + React + TS + Tailwind + TanStack Query, consuming exactly the endpoints built in this phase - a video grid (thumbnail, score badge, sort/filter -> `GET /videos`), a video detail page (score breakdown, sentiment, similar-video strip -> `GET /videos/{id}`), a channel view, and a labeling page replacing the CLI (-> `POST /labels`). Phase 6 should develop against the host-run `uv run uvicorn` API, not the containerized one, until the presigned-URL compose-networking gap is addressed. Phase 7 (Prefect orchestration) will later replace `POST /ingest`'s `BackgroundTasks` placeholder with real scheduling and retries.
