#!/usr/bin/env bash
# Restores a backup made by scripts/backup.sh.
#
# Default (SAFE): loads the backup into a throwaway scratch database next to your real one,
# prints its row counts beside the backup's manifest so you can see it is complete, then
# drops the scratch database. Your live data is not touched. Run this now and then to prove
# your backups actually restore.
#
# --replace-live: REPLACES the live database with the backup. Before anything is deleted it
# takes a fresh backup of the current database (so the replacement can itself be undone),
# then asks you to type "restore". Stop the API first (bash scripts/stop-dev.sh) so nothing
# is writing; connections that remain are cut.
#
# Usage:  bash scripts/restore-backup.sh BACKUP_FOLDER [--replace-live] [--yes]
#   BACKUP_FOLDER is one of the timestamped folders, e.g. ~/slop-or-not-backups/20261021-093015
# Needs:  the docker compose postgres service running.
set -euo pipefail
export MSYS_NO_PATHCONV=1
ORIG_PWD="$PWD"
cd "$(dirname "${BASH_SOURCE[0]}")/.."
# docker.exe is a Windows program: it needs C:/... paths, not Git Bash's /c/... form.
host_path() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi; }

BACKUP="${1:-}"
shift || true
# A relative folder means relative to where the user ran this, not to the repo root.
case "$BACKUP" in /* | [A-Za-z]:* | "") ;; *) BACKUP="$ORIG_PWD/$BACKUP" ;; esac
REPLACE=0
ASSUME_YES=0
for arg in "$@"; do
  case "$arg" in
    --replace-live) REPLACE=1 ;;
    --yes) ASSUME_YES=1 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

if [ -z "$BACKUP" ] || [ ! -f "$BACKUP/database.dump" ]; then
  echo "Usage: bash scripts/restore-backup.sh BACKUP_FOLDER [--replace-live] [--yes]" >&2
  echo "BACKUP_FOLDER must contain database.dump (a folder made by scripts/backup.sh)." >&2
  exit 2
fi

env_get() { grep -E "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '\r' || true; }
DB_USER="$(env_get POSTGRES_USER)"; DB_USER="${DB_USER:-slop}"
DB_NAME="$(env_get POSTGRES_DB)";   DB_NAME="${DB_NAME:-slopornot}"
SCRATCH="slop_restore_check"
DUMP_IN_CONTAINER="/tmp/slop_restore.dump"

pg() { docker compose exec -T postgres "$@"; }
admin() { pg psql -U "$DB_USER" -d postgres -v ON_ERROR_STOP=1 -X -q "$@"; }
counts() {
  pg psql -U "$DB_USER" -d "$1" -At -F ' = ' -X -c "
    SELECT 'channels', count(*) FROM channels UNION ALL
    SELECT 'videos', count(*) FROM videos UNION ALL
    SELECT 'comments', count(*) FROM comments UNION ALL
    SELECT 'labels', count(*) FROM labels UNION ALL
    SELECT 'video_scores', count(*) FROM video_scores UNION ALL
    SELECT 'thumbnails', count(*) FROM thumbnails" | tr -d '\r' | sed 's/^/  /'
}
cleanup() { pg rm -f "$DUMP_IN_CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT

if ! pg true >/dev/null 2>&1; then
  echo "The postgres container is not running. Start it with: docker compose up -d postgres" >&2
  exit 1
fi

if [ -f "$BACKUP/manifest.txt" ] && command -v sha256sum >/dev/null; then
  WANT="$(grep -E '^sha256:' "$BACKUP/manifest.txt" | awk '{print $2}')"
  HAVE="$(sha256sum "$BACKUP/database.dump" | cut -d' ' -f1)"
  if [ -n "$WANT" ] && [ "$WANT" != "$HAVE" ]; then
    echo "database.dump does not match the checksum in manifest.txt; the file is damaged." >&2
    exit 1
  fi
  echo "checksum ok."
fi

if ! COPY_OUT="$(docker compose cp "$(host_path "$BACKUP")/database.dump" "postgres:$DUMP_IN_CONTAINER" 2>&1)"; then
  echo "Could not copy the dump into the container:" >&2
  echo "$COPY_OUT" >&2
  exit 1
fi

if [ "$REPLACE" -eq 0 ]; then
  echo "restoring into the scratch database $SCRATCH (your live database is not touched)..."
  admin -c "DROP DATABASE IF EXISTS $SCRATCH" -c "CREATE DATABASE $SCRATCH"
  pg pg_restore -U "$DB_USER" -d "$SCRATCH" --no-owner --no-acl --exit-on-error "$DUMP_IN_CONTAINER"
  echo
  echo "restored row counts:"; counts "$SCRATCH"
  if [ -f "$BACKUP/manifest.txt" ]; then
    echo "the backup's manifest says:"
    sed -n '/row counts at backup time/,$p' "$BACKUP/manifest.txt" | tail -n +2
  fi
  admin -c "DROP DATABASE IF EXISTS $SCRATCH"
  echo
  echo "ok: this backup restores cleanly. (Scratch database removed; live data untouched.)"
  exit 0
fi

echo "This will REPLACE the live database '$DB_NAME' with the backup in $BACKUP."
echo "Current live row counts:"; counts "$DB_NAME"
if [ "$ASSUME_YES" -ne 1 ]; then
  read -r -p "Type 'restore' to continue: " answer
  if [ "$answer" != "restore" ]; then echo "Not confirmed - nothing changed."; exit 1; fi
fi

echo "taking a safety backup of the current database first..."
bash scripts/backup.sh

echo "replacing the live database..."
admin -c "DROP DATABASE IF EXISTS $DB_NAME WITH (FORCE)" -c "CREATE DATABASE $DB_NAME"
pg pg_restore -U "$DB_USER" -d "$DB_NAME" --no-owner --no-acl --exit-on-error "$DUMP_IN_CONTAINER"
echo "restored row counts:"; counts "$DB_NAME"
if [ -f "$BACKUP/data/seed_channels.csv" ] && [ ! -f data/seed_channels.csv ]; then
  mkdir -p data && cp "$BACKUP/data/seed_channels.csv" data/ && echo "restored data/seed_channels.csv"
fi
echo "done. Restart the app with: bash scripts/start-dev.sh"
