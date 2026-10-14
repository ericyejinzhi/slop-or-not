#!/usr/bin/env bash
# Builds a deployable snapshot of the local database:
#   - everything EXCEPT the raw comments (the API never exposes comment text, the features
#     derived from it are already stored, and ROADMAP.md says not to publish raw comments),
#   - video_scores reduced to the ACTIVE model's version (older model versions are noise).
# It works on a scratch copy inside the local docker postgres container, so the live
# database is never modified.
#
# Usage:  bash scripts/export-snapshot.sh [OUT_FILE]      (default: snapshot.dump)
# Needs:  the docker compose postgres service running; ACTIVE_MODEL_NAME/VERSION in .env.
# Next:   scripts/import-snapshot.sh loads the file into the target Postgres (RDS).
set -euo pipefail
# Git Bash on Windows would otherwise rewrite arguments like /tmp/x into C:\... paths.
export MSYS_NO_PATHCONV=1
cd "$(dirname "${BASH_SOURCE[0]}")/.."

OUT="${1:-snapshot.dump}"
env_get() { grep -E "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '\r' || true; }
DB_USER="$(env_get POSTGRES_USER)"; DB_USER="${DB_USER:-slop}"
DB_NAME="$(env_get POSTGRES_DB)";   DB_NAME="${DB_NAME:-slopornot}"
MODEL_NAME="$(env_get ACTIVE_MODEL_NAME)"
MODEL_VERSION="$(env_get ACTIVE_MODEL_VERSION)"
if [ -z "$MODEL_NAME" ] || [ -z "$MODEL_VERSION" ]; then
  echo "ACTIVE_MODEL_NAME and ACTIVE_MODEL_VERSION must be set in .env (they pick the scores to keep)." >&2
  exit 1
fi
SCRATCH="slop_snapshot_scratch"
DUMP_IN_CONTAINER="/tmp/snapshot.dump"

pg() { docker compose exec -T postgres "$@"; }
psql_scratch() { pg psql -U "$DB_USER" -d "$SCRATCH" -v ON_ERROR_STOP=1 -X -q "$@"; }

cleanup() {
  pg psql -U "$DB_USER" -d postgres -X -q -c "DROP DATABASE IF EXISTS $SCRATCH" >/dev/null 2>&1 || true
  pg rm -f "$DUMP_IN_CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "1/5 copying $DB_NAME into a scratch database ($SCRATCH)..."
pg psql -U "$DB_USER" -d postgres -X -q -v ON_ERROR_STOP=1 \
  -c "DROP DATABASE IF EXISTS $SCRATCH" -c "CREATE DATABASE $SCRATCH"
pg sh -c "pg_dump -U $DB_USER -Fc $DB_NAME | pg_restore -U $DB_USER -d $SCRATCH --no-owner --no-acl --exit-on-error"

echo "2/5 pruning the scratch copy (no comments; only $MODEL_NAME / $MODEL_VERSION scores)..."
psql_scratch -v name="$MODEL_NAME" -v ver="$MODEL_VERSION" <<'SQL'
TRUNCATE comments;
DELETE FROM video_scores WHERE NOT (model_name = :'name' AND model_version = :'ver');
SQL
KEPT="$(psql_scratch -At -c "SELECT count(*) FROM video_scores")"
if [ "$KEPT" -eq 0 ]; then
  echo "No scores exist for $MODEL_NAME / $MODEL_VERSION - check ACTIVE_MODEL_* in .env." >&2
  exit 1
fi

echo "3/5 row counts in the snapshot:"
psql_scratch -c "
SELECT 'channels' AS table, count(*) FROM channels UNION ALL
SELECT 'videos', count(*) FROM videos UNION ALL
SELECT 'thumbnails', count(*) FROM thumbnails UNION ALL
SELECT 'labels', count(*) FROM labels UNION ALL
SELECT 'video_scores', count(*) FROM video_scores UNION ALL
SELECT 'video_nlp_features', count(*) FROM video_nlp_features UNION ALL
SELECT 'video_vision_features', count(*) FROM video_vision_features UNION ALL
SELECT 'comments', count(*) FROM comments"

echo "4/5 dumping the scratch database..."
pg pg_dump -U "$DB_USER" -Fc --no-owner --no-acl -f "$DUMP_IN_CONTAINER" "$SCRATCH"

echo "5/5 copying the dump out of the container to $OUT..."
docker compose cp "postgres:$DUMP_IN_CONTAINER" "$OUT"

echo "done: $OUT ($(du -h "$OUT" | cut -f1)) - the live database was not modified."
echo "The thumbnails table still names the LOCAL bucket; import-snapshot.sh rewrites it."
