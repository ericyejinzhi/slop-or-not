#!/usr/bin/env bash
# Loads a snapshot made by export-snapshot.sh into an EMPTY Postgres database (e.g. RDS)
# and points the thumbnail rows at the deployment's bucket.
#
# Usage:  bash scripts/import-snapshot.sh SNAPSHOT_FILE THUMBNAILS_BUCKET
# Target: the standard libpq environment variables - PGHOST PGPORT PGUSER PGPASSWORD
#         PGDATABASE, plus PGSSLMODE=require for RDS. Needs psql and pg_restore installed
#         (on Ubuntu/Debian: apt install postgresql-client).
#
# Why the bucket argument: every thumbnails row stores the bucket name it was uploaded to
# ("thumbnails" locally), and the API builds image URLs from that stored name. A
# deployment's bucket has a different name, so the rows must be rewritten or no thumbnail
# would load. (The files themselves are copied with `slop deploy copy-thumbnails`.)
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "Usage: $0 SNAPSHOT_FILE THUMBNAILS_BUCKET" >&2
  exit 2
fi
SNAPSHOT="$1"
BUCKET="$2"

for tool in psql pg_restore; do
  command -v "$tool" >/dev/null || { echo "$tool not found - install the PostgreSQL client." >&2; exit 1; }
done
[ -f "$SNAPSHOT" ] || { echo "No such file: $SNAPSHOT" >&2; exit 1; }
[ -n "${PGDATABASE:-}" ] || { echo "Set PGDATABASE (and PGHOST/PGUSER/PGPASSWORD) first." >&2; exit 1; }

# Refuse a database that already holds data: restoring over it would mix two datasets.
# To start over, drop and recreate the database.
if [ "$(psql -X -Atq -c "SELECT to_regclass('public.videos') IS NOT NULL")" = "t" ]; then
  echo "The target database '$PGDATABASE' already has a 'videos' table." >&2
  echo "Import into an empty database (drop and recreate it to start over)." >&2
  exit 1
fi

echo "1/4 enabling the pgvector extension..."
psql -X -q -v ON_ERROR_STOP=1 -c "CREATE EXTENSION IF NOT EXISTS vector"

echo "2/4 restoring $SNAPSHOT..."
pg_restore --no-owner --no-acl --exit-on-error -d "$PGDATABASE" "$SNAPSHOT"

echo "3/4 pointing thumbnail rows at bucket '$BUCKET'..."
psql -X -q -v ON_ERROR_STOP=1 -v bucket="$BUCKET" <<'SQL'
UPDATE thumbnails SET s3_bucket = :'bucket';
ANALYZE;
SQL

echo "4/4 row counts:"
psql -X -c "
SELECT 'channels' AS table, count(*) FROM channels UNION ALL
SELECT 'videos', count(*) FROM videos UNION ALL
SELECT 'thumbnails', count(*) FROM thumbnails UNION ALL
SELECT 'labels', count(*) FROM labels UNION ALL
SELECT 'video_scores', count(*) FROM video_scores UNION ALL
SELECT 'video_nlp_features', count(*) FROM video_nlp_features UNION ALL
SELECT 'video_vision_features', count(*) FROM video_vision_features UNION ALL
SELECT 'comments', count(*) FROM comments"
echo "bucket now: $(psql -X -Atq -c "SELECT string_agg(DISTINCT s3_bucket, ', ') FROM thumbnails")"
echo "done. Next: slop deploy copy-thumbnails --dest-bucket $BUCKET"
