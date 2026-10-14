# Local rehearsal of the production setup (pre-AWS prep, 2026-10-14)

## What is being implemented

A dry run of the production-shaped stack, locally, before spending anything on AWS: rebuild both Docker images from the current code, run the nginx `web` and `api` containers with `READ_ONLY=true` and no model on disk, and check the behaviors a public server depends on. Phase 8 did a version of this earlier (see `stage-2-production-frontend-serving.md`), before read-only mode, model fetching, channel scores and most of the later changes existed. Nothing in the repo changed for this stage; it only checked. The override file used (read-only, empty model folder, fetch from a scratch bucket, API on port 18000 so it did not clash with the dev API) lived outside the repo and was deleted afterwards.

## What it should look like

```
publish the active model (logistic_regression/20261008-230715) to a scratch bucket   [ok] x2
docker compose up api web (images as built)      api healthy after ~5s
direct to the api container:  /health ok, /config {"read_only":true},
                              POST /ingest -> 403, POST /labels -> 403,
                              GET /videos -> total 1072, first score 0.803 down
through nginx (port 8080):    GET / -> 200, GET /videos/abc (SPA route) -> 200,
                              GET /api/config -> read_only true, GET /api/videos -> total 1072,
                              POST /api/ingest -> 403
fresh server: models_artifacts did not exist in the container;
              active_model_feature_needs() downloaded model.joblib (about 10 KB) and
              metadata.json from the bucket and returned (True, True)
```

## What to look out for

- **Everything checked passed on the first try.** The images rebuilt (the API image is 3.4 GB because it carries torch; the web image is 94 MB), read-only mode blocked writes both directly and through nginx, the single-page-app fallback worked for deep links, and a container that started with no model folder fetched the active model from object storage.
- **Not checked: thumbnails in a browser.** From inside a container, presigned thumbnail URLs name the compose-internal host (`http://minio:9000/...`), which a browser on the host cannot reach. That is a local-only limitation: on AWS, URLs resolve to the real S3 endpoint. (The migration rehearsal, `data-migration.md`, fetched a real thumbnail with the API running on the host.)
- **Not checked: the dashboard rendered in a browser.** Only HTTP status and API payloads were checked; clicking through the pages in `read-only` mode (Videos, Channels; no Label/Labeled/ingest form) is still worth doing once before launch.
- **The API image is large for what a read-only server needs.** Read-only mode never loads the ML models, yet the image installs torch and transformers because `sloppy.refresh` imports them at module load. Making those imports lazy would shrink memory use and startup; not done.
- The rehearsal stack read the dev Postgres, not a fresh one; a restored copy is covered in `data-migration.md`.

## How to run tests properly

```powershell
docker compose build api web
# then, with a throwaway override that sets READ_ONLY=true, FETCH_MODEL_FROM_S3=true,
# S3_BUCKET_MODELS=<scratch bucket> on the api service and an API_PORT that is free:
#   slop model publish --model-name <name> --model-version <version>   (to the scratch bucket)
#   docker compose -f docker-compose.yml -f <override.yml> up -d --no-build api web
#   curl -X POST localhost:<API_PORT>/ingest ...  -> 403
#   curl localhost:8080/ , localhost:8080/api/config
#   docker compose rm -sf api web      # NOT `docker compose down`, which also removes postgres/minio
```
