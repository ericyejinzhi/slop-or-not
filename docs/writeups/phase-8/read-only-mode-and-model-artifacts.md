# Read-only deployment mode and model artifacts in object storage (pre-AWS prep, 2026-10-07)

## What is being implemented

Two gaps that would have bitten the first public deployment, closed before any AWS resource exists.

**1. `READ_ONLY` mode.** `POST /ingest` and the label endpoints have no authentication. Behind a public URL, anyone could ingest channels (burning the YouTube API quota and the server's CPU) or write labels. With `READ_ONLY=true`:
- `create_app()` in `src/sloppy/api/app.py` installs a middleware that rejects every request whose method is not GET, HEAD or OPTIONS with `403 {"detail": "This deployment is read-only"}`. It is method-based, not endpoint-based, so a write endpoint added later is blocked by default. OPTIONS stays open so CORS preflights work.
- `GET /config` returns `{"read_only": bool}`. The dashboard reads it (`useReadOnly` in `web/src/api/hooks.ts`) and hides the ingest form and the Label/Labeled pages, so visitors do not see controls that cannot work. The UI fails open (assumes writable until told otherwise); the 403 is the real enforcement.

**2. Getting a trained model onto a server.** `models_artifacts/` is not in git, and the API and flows load the active model from a path relative to the working directory, so a fresh EC2 instance had no model.
- `src/sloppy/models/artifact_store.py`: `upload_model` / `download_model` / `ensure_local_model`. A model is `model.joblib` + `metadata.json` under `<model_name>/<model_version>/` in the bucket `S3_BUCKET_MODELS` (MinIO locally, S3 in production).
- `slop model publish --model-name X --model-version V` uploads (creating the bucket if needed); `slop model fetch ...` is the inverse.
- With `FETCH_MODEL_FROM_S3=true`, `refresh.py` downloads the active model on demand, just before it reads its feature list or scores with it, only if it is not already on disk. Off by default, so local development never touches the network for this. A failed download is logged and swallowed; the existing behavior for a missing artifact applies.
- Downloads are written to `*.part` files and renamed into place, so an interrupted download never leaves a half-written `model.joblib` that looks complete.
- Terraform (`infra/terraform/`): a second private bucket, `models_bucket_name`, and an extra IAM statement giving the app instance role **read-only** access to it.

## What it should look like

```
$ READ_ONLY=true uv run uvicorn sloppy.api.app:app
$ curl -s -X POST localhost:8000/ingest -H 'content-type: application/json' -d '{"channel":"@x"}'
{"detail":"This deployment is read-only"}                    # HTTP 403
$ curl -s localhost:8000/config
{"read_only":true}

$ uv run slop model publish --model-name logistic_regression --model-version 20261007-194834
[ok] s3://models/logistic_regression/20261007-194834/model.joblib
[ok] s3://models/logistic_regression/20261007-194834/metadata.json
# on the server, with FETCH_MODEL_FROM_S3=true, the first refresh/score downloads it
```

## What to look out for

- **`model.joblib` is a pickle.** Loading it runs whatever code it contains, so whoever can write to the models bucket can run code on every server that loads from it. That is why the bucket is private and the instance role is read-only; publish with your own credentials from your own machine. There is no signature or checksum check, because anyone who can replace the model can replace its checksum too.
- **Read-only mode only restricts writes.** Every GET stays open, including the data behind the labeled-videos list (your own labels). If those should not be public either, that is a separate decision.
- **A read-only deployment does not need the model files at all** when scores come from the `video_scores` table (which is what the API serves). The model is only needed to score newly ingested videos, which a read-only deployment cannot ingest.
- **The Terraform additions are unvalidated**: the `terraform` binary was not available, so `terraform validate` and `terraform fmt -check` were not run on them (see the Terraform README).
- **Not exercised against real AWS.** Publish/fetch were tested against the local MinIO (same boto3 API), which is a faithful stand-in for the code path but not for IAM policy behavior.

## How to run tests properly

```powershell
uv run pytest tests/test_api_read_only.py tests/test_model_artifact_store.py tests/test_refresh.py -v
#   (test_model_artifact_store.py needs the local MinIO running; it uses a throwaway bucket)
uv run ruff check . ; uv run ruff format --check .

cd web
npx tsc -b ; npx vitest run ; npm run lint
```
