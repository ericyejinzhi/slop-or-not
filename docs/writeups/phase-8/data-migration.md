# Moving the local data to a deployment (pre-AWS prep, 2026-10-14)

## What is being implemented

A cloud deployment starts with an empty database and an empty bucket; nothing existed to move the local data there. Three pieces, rehearsed end to end locally (against a scratch database and bucket, never the real ones):

1. **`scripts/export-snapshot.sh [OUT_FILE]`** builds a deployable snapshot. It copies the local database into a scratch database inside the docker postgres container, prunes the copy, and dumps it, so the live database is never modified. The prune drops all raw `comments` (the API never exposes comment text, the derived features are already stored, and ROADMAP.md says not to publish raw comments) and keeps only the active model's rows in `video_scores` (the table holds scores from every model version ever trained). Real numbers: the live database is 43 MB; the snapshot is 8.6 MB with 105 channels, 1,072 videos, 1,031 thumbnail rows, 1,110 labels, 1,072 scores, 1,072 NLP and 1,031 vision feature rows, and 0 comments.
2. **`scripts/import-snapshot.sh SNAPSHOT_FILE THUMBNAILS_BUCKET`** loads it into an EMPTY Postgres (the target comes from the standard `PGHOST`/`PGUSER`/`PGPASSWORD`/`PGDATABASE`/`PGSSLMODE` variables; needs `psql` and `pg_restore`). It enables pgvector, restores with `--no-owner --no-acl` (RDS has different roles), refuses if a `videos` table already exists, and rewrites every `thumbnails.s3_bucket` to the deployment's bucket.
3. **`slop deploy copy-thumbnails --dest-bucket B [--dest-endpoint-url U] [--dry-run]`** copies every thumbnail the database references from the local MinIO to another bucket, keeping the keys. It skips objects already there with the same size, so an interrupted copy resumes. Destination credentials come from `DEST_AWS_ACCESS_KEY_ID`/`DEST_AWS_SECRET_ACCESS_KEY` or boto3's default chain, never from the MinIO keys in `.env`. The destination bucket must already exist (Terraform creates it); a typo is an error, not a new stray bucket. Logic in `src/sloppy/storage_copy.py` (`copy_objects`).

## What it should look like

```
$ bash scripts/export-snapshot.sh snapshot.dump
...
done: snapshot.dump (8.6M) - the live database was not modified.

$ PGHOST=<rds> PGUSER=... PGPASSWORD=... PGDATABASE=slopornot PGSSLMODE=require \
    bash scripts/import-snapshot.sh snapshot.dump <thumbnails-bucket>
...
bucket now: <thumbnails-bucket>

$ slop deploy copy-thumbnails --dest-bucket <thumbnails-bucket> --dry-run
[ok] would copy 1031 (131.1 MB), 0 already there
$ slop deploy copy-thumbnails --dest-bucket <thumbnails-bucket>
[ok] copied 1031 (131.1 MB), 0 already there
```

## What to look out for

- **The bucket name is stored per row.** Every `thumbnails` row records the bucket it was uploaded to (`thumbnails` locally), and the API builds image URLs from that stored name, not from settings. A deployment's bucket is named differently, so without the rewrite in step 2 every thumbnail would 404. This was found by inspecting the data while planning, not by a failure.
- **Rehearsed, not deployed.** The rehearsal restored the snapshot into a scratch database (`slop_restore_test`) via the import script run inside the postgres container, copied the thumbnails into a scratch MinIO bucket, ran the API against that pair with `READ_ONLY=true`, and fetched a real thumbnail through it: HTTP 200, 116 KB. Videos (1,072), channel scores (105 channels), NLP and vision features, and pgvector similar-videos all worked, and `POST /ingest` returned 403. It has not been run against real RDS or S3, so RDS-specific behavior (for example whether `rds_superuser` can create the `vector` extension in your instance's parameter group) is untested.
- **The thumbnails are WebP data.** The rehearsal's fetched file starts with `RIFF` (a WebP container) even though the keys end in `.jpg`; browsers sniff it, so it renders, but the extension is misleading.
- **The snapshot has no raw comments but does have labels** (your judgments) and everything the dashboard shows. The labeled-videos page is hidden in read-only mode, but the data is in the database. Delete the `labels` rows from the scratch copy in the export script if that should not be public.
- **A snapshot is a point in time.** Re-exporting and re-importing means a new empty database (drop and recreate), and scores are only for the model that was active at export time. For later updates the cloud server would need the ingest/refresh path (not enabled in a read-only deployment).
- `scripts/export-snapshot.sh` uses `docker compose exec` against the repo's own compose project, so run it from the main checkout (a git worktree has a different compose project name unless `COMPOSE_PROJECT_NAME` is set).

## How to run tests properly

```powershell
uv run pytest tests/test_storage_copy.py -v     # needs the local MinIO running; uses throwaway buckets
uv run ruff check . ; uv run ruff format --check .

# the shell scripts are rehearsed by hand, as described above, rather than unit-tested:
bash scripts/export-snapshot.sh snapshot.dump
```
