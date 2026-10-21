#!/usr/bin/env bash
# Backs up what cannot be re-created from YouTube. Your labels are hand work, and ingestion
# samples videos at random, so re-ingesting a channel would not bring back the same videos.
#
# One timestamped folder per backup, containing:
#   database.dump   the WHOLE local database (pg_dump custom format): labels, videos, comments,
#                   scores, features. This is what restore-backup.sh loads.
#   labels.csv      every label ever recorded (the table is append-only history), with channel
#                   and video titles. Plain text, readable without Postgres, as a second copy
#                   of the most valuable data.
#   data/           data/seed_channels.csv and data/splits.csv, if present.
#   manifest.txt    when, from which code version, row counts, and the dump's checksum.
# NOT included: thumbnails (131 MB, re-downloadable by video id) and trained models
# (re-trainable). The object storage volume can be copied by hand if you want them.
#
# Safe to run while the app is running: pg_dump reads a consistent snapshot and changes nothing.
# Writes into a ".partial" folder and renames it only when verified, so an interrupted run never
# leaves something that looks like a good backup. Keeps the newest BACKUP_KEEP (default 14).
#
# Usage:  bash scripts/backup.sh [BACKUP_ROOT]
#   BACKUP_ROOT defaults to $BACKUP_DIR, else ~/slop-or-not-backups. Keep it OUTSIDE the repo
#   (and ideally on another drive or synced folder), so one mistake cannot take both.
# Needs:  the docker compose postgres service running.
set -euo pipefail
# Git Bash on Windows would otherwise rewrite arguments like /tmp/x into C:\... paths.
export MSYS_NO_PATHCONV=1
ORIG_PWD="$PWD"
cd "$(dirname "${BASH_SOURCE[0]}")/.."

ROOT="${1:-${BACKUP_DIR:-$HOME/slop-or-not-backups}}"
# A relative folder means relative to where the user ran this, not to the repo root we just moved to.
case "$ROOT" in /* | [A-Za-z]:*) ;; *) ROOT="$ORIG_PWD/$ROOT" ;; esac
# docker.exe is a Windows program: it needs C:/... paths, not Git Bash's /c/... form.
host_path() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi; }
KEEP="${BACKUP_KEEP:-14}"
env_get() { grep -E "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '\r' || true; }
DB_USER="$(env_get POSTGRES_USER)"; DB_USER="${DB_USER:-slop}"
DB_NAME="$(env_get POSTGRES_DB)";   DB_NAME="${DB_NAME:-slopornot}"

pg() { docker compose exec -T postgres "$@"; }
psql_live() { pg psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -X -q "$@"; }

if ! pg true >/dev/null 2>&1; then
  echo "The postgres container is not running, so there is nothing to back up." >&2
  echo "Start it with: docker compose up -d postgres" >&2
  exit 1
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
FINAL="$ROOT/$STAMP"
WORK="$FINAL.partial"
DUMP_IN_CONTAINER="/tmp/slop_backup.dump"
mkdir -p "$WORK/data"
cleanup() { pg rm -f "$DUMP_IN_CONTAINER" >/dev/null 2>&1 || true; }
# On ANY exit: drop the temp dump in the container and any unfinished .partial folder. After
# a successful run the .partial folder has been renamed away, so there is nothing to remove.
trap 'cleanup; rm -rf "$WORK"' EXIT

echo "1/5 dumping the database ($DB_NAME)..."
pg pg_dump -U "$DB_USER" -Fc -f "$DUMP_IN_CONTAINER" "$DB_NAME"
ENTRIES="$(pg pg_restore -l "$DUMP_IN_CONTAINER" | grep -c . || true)"
if [ "$ENTRIES" -lt 10 ]; then
  echo "The dump looks empty or unreadable ($ENTRIES entries); not keeping it." >&2
  exit 1
fi
if ! COPY_OUT="$(docker compose cp "postgres:$DUMP_IN_CONTAINER" "$(host_path "$WORK")/database.dump" 2>&1)"; then
  echo "Could not copy the dump out of the container:" >&2
  echo "$COPY_OUT" >&2
  exit 1
fi

echo "2/5 exporting every label to labels.csv..."
psql_live -c "\\copy (
  SELECT l.id, l.video_id, v.title AS video_title, v.channel_id, c.title AS channel_title,
         l.labeler, l.label, l.notes, l.created_at, l.updated_at
  FROM labels l
  LEFT JOIN videos v ON v.id = l.video_id
  LEFT JOIN channels c ON c.id = v.channel_id
  ORDER BY l.id) TO STDOUT WITH CSV HEADER" > "$WORK/labels.csv"

echo "3/5 copying data files..."
for f in data/seed_channels.csv data/splits.csv; do
  [ -f "$f" ] && cp "$f" "$WORK/data/"
done

echo "4/5 checking the backup against the live database..."
LIVE_LABELS="$(psql_live -At -c "SELECT count(*) FROM labels" | tr -d '\r')"
CSV_LABELS="$(python -c "import csv,sys; print(sum(1 for _ in csv.reader(open(sys.argv[1], encoding='utf-8', newline=''))) - 1)" "$(host_path "$WORK")/labels.csv")"
if [ "$LIVE_LABELS" != "$CSV_LABELS" ]; then
  echo "labels.csv has $CSV_LABELS rows but the database has $LIVE_LABELS; not keeping this backup." >&2
  exit 1
fi
DUMP_BYTES="$(wc -c < "$WORK/database.dump" | tr -d ' ')"
if [ "$DUMP_BYTES" -lt 1000 ]; then
  echo "database.dump is only $DUMP_BYTES bytes; not keeping this backup." >&2
  exit 1
fi

{
  echo "backup:   $STAMP"
  echo "code:     $(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
  echo "database: $DB_NAME ($ENTRIES objects in the dump, $DUMP_BYTES bytes)"
  echo "sha256:   $(sha256sum "$WORK/database.dump" | cut -d' ' -f1)"
  echo "row counts at backup time:"
  psql_live -At -F ' = ' -c "
    SELECT 'channels', count(*) FROM channels UNION ALL
    SELECT 'videos', count(*) FROM videos UNION ALL
    SELECT 'comments', count(*) FROM comments UNION ALL
    SELECT 'labels', count(*) FROM labels UNION ALL
    SELECT 'video_scores', count(*) FROM video_scores UNION ALL
    SELECT 'thumbnails', count(*) FROM thumbnails" | tr -d '\r' | sed 's/^/  /'
} > "$WORK/manifest.txt"

echo "5/5 finishing..."
mv "$WORK" "$FINAL"

# Retention: keep the newest $KEEP complete backups. Only folders named like a timestamp are
# ever considered, so nothing else in the folder can be deleted by this.
mapfile -t ALL < <(ls -1 "$ROOT" | grep -E '^[0-9]{8}-[0-9]{6}$' | sort)
if [ "${#ALL[@]}" -gt "$KEEP" ]; then
  for old in "${ALL[@]:0:${#ALL[@]}-KEEP}"; do
    rm -rf "${ROOT:?}/$old"
    echo "  removed old backup $old"
  done
fi

echo "done: $FINAL"
echo "  $LIVE_LABELS labels, $(( DUMP_BYTES / 1024 )) KB dump. ${#ALL[@]} backup(s) kept (max $KEEP)."
