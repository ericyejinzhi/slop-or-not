# Phase 2, Stage 2 - `labels` table + labeler identity

## What is being implemented

The database schema for recording labeling judgments, plus a way to identify who made each one. No labeling CLI yet - this is schema only, mirroring how Phase 1 Stage 1 built the ingestion tables before any pipeline touched them.

Files: `src/sloppy/db/models.py` (add `Label`), `alembic/versions/c7d2681646c2_add_labels_table.py`, `src/sloppy/config.py` (add `labeler_name`), `.env.example` and `.env` (add `LABELER_NAME=`), `tests/test_db_models.py` (extended).

## What it should look like

- `psql \d labels` should show: `id` (integer PK, autoincrement), `video_id` (text, FK -> `videos.id`, indexed), `labeler` (text), `label` (text), `notes` (nullable text), `created_at`/`updated_at`. A check constraint restricts `label` to exactly `'up'`, `'down'`, or `'skip'`.
- `uv run alembic current` should print `c7d2681646c2 (head)`.
- `uv run pytest` should show 19 passing tests (the existing suite, with `test_db_models.py` now also asserting `labels` is registered and its FK points at `videos`).
- `uv run slop smoke` should still pass unchanged.

## What to look out for

- **`video_id` is deliberately NOT unique.** A video can have multiple label rows over time - this is required by the roadmap's own verify step ("spot-check consistency by relabeling 20 videos a week later"). The primary key is a synthetic autoincrement `id`, not `video_id` itself. This is different from every Phase 1 table, which all used upsert-on-conflict semantics keyed on YouTube's own ids - labels are an event log, not a "current state" table.
- **No `severity` column exists yet, on purpose.** The roadmap explicitly says to decide whether a 0-3 severity score is worth adding only after the first ~50 real labels - adding a nullable column now would be guessing at a name/scale before that decision is made. If you do want it later, that's a one-line-model-change + one-migration addition, not a redesign.
- **The check constraint was verified directly**, not just trusted: I tried inserting a row with `label='maybe'` straight through `psql` and confirmed Postgres rejects it with `ck_labels_label_value` - this isn't just enforced at the Python/ORM layer, it's a real DB-level guarantee.
- **`labeler_name` is blank in your `.env`** right now (confirmed by loading `Settings` directly) - nothing in this stage requires it yet, but the Stage 5 labeling CLI will read it as the default and refuse to run if neither `.env`'s `LABELER_NAME` nor a `--labeler` flag is set. Fill it in whenever you like before Stage 5.
- The migration was reviewed before applying (matches the model definitions exactly) and round-tripped with `alembic downgrade -1` / `upgrade head` to confirm reversibility.

## How to run tests properly

```powershell
# 1. Make sure Postgres/MinIO are up
docker compose up -d

# 2. Run the test suite
uv run pytest

# 3. Confirm migration state and inspect the schema directly
uv run alembic current
docker compose exec postgres psql -U slop -d slopornot -c "\d labels"

# 4. Confirm the migration is reversible (optional but worth doing once)
uv run alembic downgrade -1
uv run alembic upgrade head

# 5. Confirm the check constraint is real, not just an ORM-side assumption
docker compose exec postgres psql -U slop -d slopornot -c \
  "INSERT INTO labels (video_id, labeler, label) VALUES ('nonexistent', 'test', 'maybe');"
# should fail with: ERROR - new row for relation "labels" violates check constraint "ck_labels_label_value"

# 6. Confirm Phase 0/1 didn't regress
uv run slop smoke
```
