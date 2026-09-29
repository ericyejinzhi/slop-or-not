# Phase 5, Stage 4 - Presigned thumbnail URLs

## What is being implemented

A new function `generate_presigned_url(client, bucket, key, expires_in=3600) -> str` added to `src/sloppy/storage.py`, alongside the existing `get_s3_client`/`ensure_bucket`. Until now, every read of a thumbnail went through a direct, authenticated `get_object` call (e.g. `label/display.py`'s `cache_thumbnail`) - there was no way to hand a browser a URL it could load directly. This function produces a time-limited, unauthenticated GET URL suitable for a `<img src="...">` tag, which the videos router (Stage 5) uses for every thumbnail it returns.

## What it should look like

```python
>>> client = get_s3_client(settings)
>>> generate_presigned_url(client, "thumbnails", "video123.jpg", expires_in=60)
'http://localhost:9000/thumbnails/video123.jpg?X-Amz-Algorithm=...&X-Amz-Expires=60&...'
```

Verified for real against the dev MinIO: a fixture object was uploaded via `put_object`, a presigned URL generated, and then fetched with a plain `httpx.get()` (not boto3, not any authenticated client) - confirming the URL is genuinely usable by something with zero AWS/MinIO credentials, the same way a browser would use it.

## What to look out for

- **The most important gotcha in this whole phase**: the endpoint baked into a presigned URL is whatever `settings.s3_endpoint_url` the client was built with *at generation time*. Running the API via plain `uv run uvicorn` locally (against `.env`'s `http://localhost:9000`) produces URLs a browser can load directly, since MinIO's port is published to the host. Once Stage 9 adds a docker-compose `api` service that resolves `S3_ENDPOINT_URL=http://minio:9000` on the compose-internal network, presigned URLs generated *there* will embed `http://minio:9000` - a hostname meaningless outside Docker's internal network, so a browser hitting them gets a connection failure. This is flagged again in Stage 9 and is an explicit, accepted follow-up (e.g. a separate public-facing endpoint setting, or a reverse proxy) - not solved in Phase 5.
- `generate_presigned_url` takes an already-constructed `client` as its first argument (matching `ensure_bucket`'s signature style), not a `Settings` object - every router already holds a client via the `get_s3` dependency, so this avoids reconstructing one per call.
- The function is a thin wrapper with no error handling of its own - if `key` doesn't exist in the bucket, `generate_presigned_url` still succeeds (it doesn't check existence), and the URL simply 404s on GET. This is standard S3/MinIO behavior and not something worth guarding against here.

## How to run tests properly

```powershell
uv run pytest tests/test_storage_presigned.py -v
uv run pytest    # full suite
uv run ruff check .
```

The one test in `tests/test_storage_presigned.py` is a real integration test against the dev MinIO (`docker compose up -d` required) - no fake/mocked S3 client, since the entire point of this feature is that the URL works against the real running service, which a mocked client couldn't prove.
