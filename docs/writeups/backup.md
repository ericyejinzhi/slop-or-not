# Backing up your labels (and everything else you cannot re-create)

## Why
Your labels are hand work. They cannot be rebuilt from YouTube, and neither can the rest of the dataset: ingestion samples videos at random, so re-ingesting a channel does not bring back the same videos or their comments. The local Docker volumes held the only copy, and one `docker compose down -v` or a corrupted volume would have taken it. AWS is only a read-only copy of a snapshot, so it is not a backup either (its snapshot carried no comments and was deleted from S3 after the deploy).

## What a backup contains
`bash scripts/backup.sh` writes one timestamped folder (default `~/slop-or-not-backups/YYYYMMDD-HHMMSS/`):

| File | What it is |
|---|---|
| `database.dump` | the whole database in Postgres custom format: labels, videos, comments, scores, features |
| `labels.csv` | every label ever recorded (the table is append-only history) with channel and video titles. Plain text, readable without Postgres, a second copy of the most valuable data |
| `data/` | `seed_channels.csv` and `splits.csv`, if present |
| `manifest.txt` | when, which code version, row counts, and the dump's SHA-256 |

Not included: thumbnails (about 131 MB, re-downloadable by video id) and trained models (re-trainable). Copy the MinIO volume by hand if you want them.

## How it stays trustworthy
- It reads a consistent snapshot, changes nothing, and is safe to run while the app is running.
- It writes into a `.partial` folder and renames it only after checking the dump is readable and that `labels.csv` has exactly as many rows as the live `labels` table. An interrupted or failed run leaves nothing that looks like a good backup.
- It keeps the newest 14 (`BACKUP_KEEP`). Only folders named like a timestamp are ever deleted, so nothing else in the backup folder can be removed by it.

## Using it
```
bash scripts/backup.sh                      # a backup now
bash scripts/backup.sh D:/Backups/slop      # to a folder of your choice (BACKUP_DIR works too)
bash scripts/stop-dev.sh                    # backs up automatically, then stops everything
bash scripts/stop-dev.sh --no-backup        # ...skipping the backup
```
Stopping work with `stop-dev.sh` is the usual trigger, so the habit you already have protects your labelling. A failed backup there is reported loudly and never blocks stopping.

**Put the backup folder somewhere other than the repo, ideally on another drive or a synced folder.** The default is your home folder, which protects against a lost Docker volume but not against a dead disk.

## Restoring
```
bash scripts/restore-backup.sh ~/slop-or-not-backups/20261021-093015
```
By default this is a SAFE check: it loads the backup into a throwaway database, compares row counts with the manifest, and drops it, leaving live data untouched. Run it now and then to prove your backups actually restore.

To really replace the live database:
```
bash scripts/stop-dev.sh --no-backup        # stop the API so nothing is writing
docker compose up -d postgres
bash scripts/restore-backup.sh <folder> --replace-live
```
It first takes a fresh backup of the current database (so the replacement can itself be undone), then makes you type `restore`. It refuses a dump whose checksum does not match the manifest.

## Testing
`bash scripts/test-backup.sh` checks retention, that nothing else in the folder is deleted, that a restore matches the manifest, that a damaged file is refused, and `--replace-live` against a throwaway database (it simulates losing half the labels and restores them). It never touches your real database and restores `.env` on any exit.

## What to look out for
- **Windows paths.** Docker is a Windows program, so the scripts convert Git Bash's `/c/Users/...` paths to `C:/...` before handing them over. Found by the self-test: the first version failed silently on the default folder.
- **A backup is only as good as the place it lives.** Same disk, same fate.
- **Not scheduled.** Nothing runs on a timer; the Docker database has to be running to be dumped anyway. If you want a daily backup, add a Windows Task Scheduler entry that runs `bash scripts/backup.sh` while the stack is up.
- **Restoring over a newer database loses newer work.** `--replace-live` takes a safety backup first for exactly that reason.
