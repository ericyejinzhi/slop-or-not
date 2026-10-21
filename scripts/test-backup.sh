#!/usr/bin/env bash
# Self-test for scripts/backup.sh and scripts/restore-backup.sh. Run it after changing either.
#
# It uses your real local database READ-ONLY (backups only read) and does everything
# destructive - including simulating data loss and --replace-live - against a THROWAWAY
# database named slop_selftest, never your real one. All backups go to a temp folder, never
# to ~/slop-or-not-backups, so it cannot prune your real backups.
#
# While it runs it points .env at the throwaway database; the original .env is put back on
# any exit, including Ctrl-C.
#
# Usage:  bash scripts/test-backup.sh        (needs the docker compose postgres service running)
set -uo pipefail
export MSYS_NO_PATHCONV=1
cd "$(dirname "${BASH_SOURCE[0]}")/.."
REPO="$PWD"
T="$(mktemp -d)"
export BACKUP_DIR="$T/safety"
PASS=0; FAIL=0
check() { if [ "$2" = "ok" ]; then echo "PASS  $1"; PASS=$((PASS+1)); else echo "FAIL  $1  ($2)"; FAIL=$((FAIL+1)); fi; }
host_path() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi; }

DB_USER="$(grep -E '^POSTGRES_USER=' .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '\r')"; DB_USER="${DB_USER:-slop}"
ENV_COPY="$T/env.original"
[ -f .env ] && cp .env "$ENV_COPY"
pgx() { docker compose exec -T postgres "$@"; }
cleanup() {
  if [ -f "$ENV_COPY" ]; then cp "$ENV_COPY" "$REPO/.env"; fi
  pgx psql -U "$DB_USER" -d postgres -X -q -c "DROP DATABASE IF EXISTS slop_selftest WITH (FORCE)" >/dev/null 2>&1 || true
  rm -rf "$T"
}
trap cleanup EXIT

if ! pgx true >/dev/null 2>&1; then
  echo "The postgres container is not running. Start it with: docker compose up -d postgres" >&2
  exit 2
fi

echo "=== A. retention: KEEP=2 with 3 backups; unrelated folders must survive"
mkdir -p "$T/root/notes-keep-me"; echo hi > "$T/root/notes-keep-me/a.txt"
for _ in 1 2 3; do BACKUP_KEEP=2 bash scripts/backup.sh "$T/root" >/dev/null 2>&1; sleep 1.3; done
N=$(ls "$T/root" | grep -cE '^[0-9]{8}-[0-9]{6}$')
[ "$N" = "2" ] && check "only the newest 2 backups are kept" ok || check "only the newest 2 backups are kept" "found $N"
[ -f "$T/root/notes-keep-me/a.txt" ] && check "an unrelated folder in the backup root is never touched" ok || check "unrelated folder survives" "deleted"
[ -z "$(ls -d "$T"/root/*.partial 2>/dev/null)" ] && check "no .partial leftovers" ok || check "no .partial leftovers" "found some"

GOOD=$(ls -d "$T"/root/2*/ | tail -1); GOOD=${GOOD%/}
for f in database.dump labels.csv manifest.txt; do
  [ -s "$GOOD/$f" ] && check "backup contains $f" ok || check "backup contains $f" "missing or empty"
done

echo "=== B. restoring into the scratch database matches the manifest; live data untouched"
OUT=$(bash scripts/restore-backup.sh "$GOOD" 2>&1); RC=$?
{ [ $RC -eq 0 ] && echo "$OUT" | grep -q "restores cleanly"; } && check "default restore succeeds" ok || check "default restore" "rc=$RC"
A=$(echo "$OUT" | sed -n '/restored row counts/,/the backup.s manifest/p' | grep ' = ' | sort)
B=$(echo "$OUT" | sed -n "/the backup's manifest says/,\$p" | grep ' = ' | sort)
[ -n "$A" ] && [ "$A" = "$B" ] && check "restored row counts equal the manifest's" ok || check "row counts equal manifest" "differ"

echo "=== C. a damaged dump is detected"
cp -r "$GOOD" "$T/damaged"; printf 'x' >> "$T/damaged/database.dump"
OUT=$(bash scripts/restore-backup.sh "$T/damaged" 2>&1); RC=$?
{ [ $RC -ne 0 ] && echo "$OUT" | grep -q "damaged"; } && check "restore refuses a file that fails its checksum" ok || check "damaged dump refused" "rc=$RC"

echo "=== D. no database: fails clearly and creates nothing"
OUT=$(COMPOSE_PROJECT_NAME=no-such-project bash scripts/backup.sh "$T/none" 2>&1); RC=$?
{ [ $RC -ne 0 ] && echo "$OUT" | grep -q "not running"; } && check "backup says postgres is not running" ok || check "clear error without postgres" "rc=$RC"
[ ! -d "$T/none" ] && check "and creates nothing" ok || check "creates nothing" "folder exists"

echo "=== E. --replace-live against the throwaway database"
sed -i 's/^POSTGRES_DB=.*/POSTGRES_DB=slop_selftest/' .env
pgx psql -U "$DB_USER" -d postgres -X -q -c "DROP DATABASE IF EXISTS slop_selftest WITH (FORCE)" -c "CREATE DATABASE slop_selftest" >/dev/null 2>&1
docker compose cp "$(host_path "$GOOD")/database.dump" postgres:/tmp/selftest.dump >/dev/null 2>&1
pgx pg_restore -U "$DB_USER" -d slop_selftest --no-owner --no-acl --exit-on-error /tmp/selftest.dump >/dev/null 2>&1
pgx rm -f /tmp/selftest.dump
count() { pgx psql -U "$DB_USER" -d slop_selftest -At -X -c "select count(*) from labels" 2>/dev/null | tr -d '\r'; }
BEFORE=$(count); echo "  labels in the throwaway copy: $BEFORE"
[ -n "$BEFORE" ] && [ "$BEFORE" -gt 0 ] || { check "throwaway database set up" "no labels loaded"; exit 1; }
pgx psql -U "$DB_USER" -d slop_selftest -X -q -c "DELETE FROM labels WHERE id % 2 = 0" >/dev/null 2>&1
DAMAGED=$(count); echo "  after simulated loss: $DAMAGED"
echo "nope" | bash scripts/restore-backup.sh "$GOOD" --replace-live >/dev/null 2>&1; RC=$?
{ [ $RC -ne 0 ] && [ "$(count)" = "$DAMAGED" ]; } && check "a wrong confirmation changes nothing" ok || check "wrong confirmation" "rc=$RC"
bash scripts/restore-backup.sh "$GOOD" --replace-live --yes >"$T/replace.log" 2>&1; RC=$?
{ [ $RC -eq 0 ] && [ "$(count)" = "$BEFORE" ]; } && check "--replace-live restores every label ($BEFORE)" ok || check "--replace-live" "rc=$RC count=$(count)"
grep -q "taking a safety backup" "$T/replace.log" && check "it took a safety backup of the current state first" ok || check "safety backup" "not mentioned"
SAFE=$(ls "$T/safety" 2>/dev/null | grep -cE '^[0-9]{8}-[0-9]{6}$')
[ "$SAFE" -ge 1 ] && check "the safety backup exists" ok || check "the safety backup exists" "none"

echo
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" = "0" ]
