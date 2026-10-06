# External setup TODO

Everything in this list is a manual, external-to-the-codebase step - an account, a credential, or human judgment work (research, labeling) that no amount of code can do for you. Items 1 and 4 are done (a real API key, a labeler name set). Item 2 is in progress (60 of an eventual ~100-150 channels). Items 3, 5, 6 and 7 were completed for real on 2026-10-05 against a freshly re-ingested 60-channel corpus (626 videos, 646 labels, per-channel batch labeling): splits generated, NLP + vision features computed, and both baseline models trained and evaluated. The first real results are in `docs/writeups/phase-3/real-data-first-run.md` (inflated by channel leakage - do not quote) and the honest channel-grouped cross-validation numbers are in `docs/writeups/phase-3/cross-validation.md`.

For each item: what to do, why it matters, and which writeup(s) tell you exactly how to confirm you did it right - most of them end with "How to verify" pointing at a real command and real expected output already documented from testing that stage.

---

## Blocking now - needed before any of this pipeline touches real data

### 1. Get a YouTube Data API v3 key

**Status: done** - a real key is set in `.env`'s `YOUTUBE_API_KEY`. Verified for real: `channels.list?forHandle=kurzgesagt` returned the real channel (25.6M subscribers, 391 videos), and `slop ingest inspect-channel @kurzgesagt` printed real recent uploads with real titles/topics.

- **Verify with:** `docs/writeups/phase-1/stage-2-youtube-client-metadata.md` and `stage-3-youtube-client-comments.md` - run `slop ingest inspect-channel <a real @handle>` and `slop ingest inspect-video <a real video id>`, cross-check the printed title/stats against the real YouTube page.
- **Noted while verifying**: `slop` CLI invocations now take noticeably longer to start (tens of seconds) than in earlier phases, even for a trivial command like `inspect-channel` - `cli.py` imports `sloppy.flows.refresh` (pulls in `prefect`) and `sloppy.features.pipeline` (pulls in `torch`/`transformers`/`sentence-transformers` transitively) at module level, so every command pays that import cost now, not just ML-heavy ones. Not a bug, just a real, growing cold-start cost worth knowing about - a future optimization would be making those imports lazy (only inside the commands that actually need them), not attempted here.

### 2. Curate `data/seed_channels.csv`

**Status: in progress** - 60 real channels across 9 genres, all handles verified against the real YouTube API (`channels.list?forHandle=...` returns exactly one result for each). All rows now have real handles (the original 11 placeholder rows were filled in; a second batch of 26 new channels was added in this session, continuing the same real-API-verification process). Target is ~100-150 total, reached iteratively across sessions, not in one pass.

- **Methodology change**: the project originally planned per-video labeling (shuffled, one judgment per video - see `ROADMAP.md`'s Phase 2 section). After starting real labeling, it became clear most channels are internally consistent enough that per-video labeling mostly re-derives the channel's own reputation for little marginal signal per click. The labeling unit was changed to **channel-batch**: ingest a small random sample (default 10, from each channel's last ~75 uploads - see `slop ingest channel --help`) per channel, across many more channels, and label a whole batch with one judgment. This is a deliberate reversal of the roadmap's original "never channel-by-channel" guidance, made explicitly, not accidentally - per-video labeling (`slop label run --mode video` or the web dashboard's "By video" toggle) is still available for ad hoc exceptions, and the `/labeled` web page lets you relabel any individual video found to disagree with its channel's batch judgment.
- Two handles needed correction via real-API verification this session, same as the original batch: `@practicalengineering` resolved to an unrelated 210-subscriber channel (the real one is `@PracticalEngineeringChannel`), and `@CollegeHumor` doesn't resolve at all (the channel rebranded - real handle is `@Dropout`).
- Read `docs/rubric.md` before labeling - it's the definition of "slop" being implicitly applied in the `expected_lean` column and, later, in every actual label (now applied per-channel-batch, not per-video).
- **Verify with:** `docs/writeups/phase-2/stage-3-seed-channels.md` (run `slop label seed-status` after ingesting - see item 3 below) and `docs/writeups/phase-2/stage-4-pool-selection.md` (run `slop label pool-preview` to sanity-check genre/channel balance before labeling).

### 3. Bulk-ingest the curated channel list

**Status: done (re-done 2026-10-05).** All ingested data was deliberately wiped (every table plus the MinIO `thumbnails` bucket) and the 60 seed channels were re-ingested from scratch with the default 10-video random sample per channel: 60 channels, 626 videos, 42,386 comments, 617 thumbnails. The old per-video labels were backed up first to `.dev-logs/labels-backup-20261002.sql` (gitignored) and were not restored, since the random samples mostly picked different videos. The original run, for the record: the first 34 channels at 30 most-recent videos/channel gave 690 videos, 51,857 comments, 671 thumbnails. New ingestion defaults to a random 10-video sample (channel-batch methodology, item 2). `ingest_seed_channels`/`ingest channel` now default to `--sample-window 75 --sample-size 10` (random sample, not most-recent-N) - pass `--max-videos-per-channel`/`--max-videos` to opt back into the old most-recent-N behavior if ever needed. Re-run `slop ingest seed-channels` to pull in the 26 newly-added channels from item 2 - it already skips the channels done so far.

- Once the API key and CSV are in place: `uv run slop ingest seed-channels`.
- **Real bug found and fixed while first attempting this**: `ingest_channel` originally pulled a channel's *entire* upload history unconditionally - several of the real channels drafted for `seed_channels.csv` (PewDiePie, Markiplier, jacksepticeye) have thousands of videos, which would have meant thousands of comment-fetch + thumbnail-download calls per channel, burning far more quota and time than intended. Fixed: `ingest_channel`/`ingest_video` gained a `limit` parameter (most-recent-N). Caught before any real ingestion ran.
- **Second fix**: `ingest seed-channels` now skips any CSV row whose `Channel.handle` already has `last_ingested_at` set (case-insensitive match). Pass `--force` to re-ingest everything anyway. Covered by `tests/test_cli_seed_channels.py`.
- **Pending manual step: trim the original 34 channels down to 10 videos each**, to match the new channel-batch sample size. The code for this is built and tested (`slop ingest trim-channel <handle> --keep 10` / `slop ingest trim-all --keep 10`, in `src/sloppy/ingest/trim.py`) but **has not been run against the real corpus yet** - it requires an explicit go-ahead since it deletes data (comments/thumbnails, DB rows and the real S3/MinIO objects) for the videos not kept. It is safe to run even with real labels present: any video that already has a label is always kept, never deleted, even if that means keeping more than 10 for a channel (confirmed via `tests/test_ingest_trim.py::test_trim_channel_to_sample_never_deletes_an_already_labeled_video`).
- **Verify with:** `docs/writeups/phase-1/phase-1-overview.md` (row-count sanity checks via `psql`) and `docs/writeups/phase-2/stage-3-seed-channels.md` (`slop label seed-status`). For the skip behavior: `uv run pytest tests/test_cli_seed_channels.py -v`. For trimming: `uv run pytest tests/test_ingest_trim.py -v`.

### 4. Set `LABELER_NAME` in `.env`

**Status: done** - set to `eric`. Confirmed loaded correctly via `get_settings().labeler_name`.

- Can be overridden per-run with `slop label run --labeler <name>` if multiple people ever label.
- **Verify with:** `docs/writeups/phase-2/stage-2-labels-table.md` and `stage-5-labeling-cli.md` - `slop label run` refuses to start with neither set, so successfully starting a session confirms this is wired up.

### 5. Actually label videos

**Status: done for the current 60-channel corpus (2026-10-05)** - 646 labels (428 up / 200 down / 18 skip; about 32% down, above the roadmap's 25% minority floor), all via the web dashboard's labeling page. Every non-skip video in a channel carries the channel's judgment, and two channels (`@bingingwithbabish`, `@mrbeast`) are skip-only so they drop out of training. More labeling will be needed as the seed list grows toward ~100-150 channels. Earlier status for reference: 120 labels (63 up / 55 down / 2 skip) before the re-ingest. Labeling is now **channel-batch by default**: `/label` shows one channel's sampled videos at a time and applies one judgment to the whole batch (`GET /labels/channel-pool` + `POST /labels/batch`). Per-video labeling is still available (the "By video" toggle on the same page, or `slop label run --mode video` in the CLI) for ad hoc exceptions, and `/labeled` lets you search for and relabel any individual video.

- Web: open `/label` (channel mode is the default). CLI: `uv run slop label run --limit 50` (now defaults to `--mode channel`; pass `--mode video` or `--mode consistency` for the other two modes).
- Read `docs/rubric.md` before a session - the rubric's per-video judgment calls still apply, just now applied once per channel's whole sampled batch rather than per individual video.
- **Verify with:** `uv run slop label stats` (per-channel/overall counts, minority-class share) and `docs/writeups/phase-2/stage-7-consistency-and-stats.md`.

### 6. Generate the train/val/test split

**Status: done (2026-10-06), grouped by channel.** `uv run slop label make-splits` defaults to `--group-by channel`: whole channels per split, so no channel spans train and test. A `--group-by video` option (label-stratified random split ignoring channels) was added on 2026-10-05 and briefly made the default, then reverted: labels are per channel, so a by-video split leaks channel identity into the test set (see item 7 for how large the effect was). The by-video run produced 608 labeled videos, train 426 / val 91 / test 91, about 31-32% down in each.

- **Prefer `slop model cv` for estimating performance.** With about 58 labeled channels, one 15% val/test split is only 8-9 channels and very noisy. `slop model cv` runs stratified k-fold grouped by channel instead (`docs/writeups/phase-3/cross-validation.md`).
- **Verify with:** `docs/writeups/phase-2/stage-6-train-val-test-split.md` (see its 2026-10-05/06 update) - under `--group-by channel` no channel spans two splits; the command prints each split's size and down share.

### 7. Train and evaluate the baseline model

**Status: done (2026-10-05/06); the honest number is now in.** NLP features (all 626 videos, including a real-data bug fix - comments over 512 tokens crashed `compute-nlp`, now truncated) and vision features (617 videos) were computed, then both baseline models were trained and evaluated.

- **Honest result (channel-grouped, `slop model cv`, 5 folds x 3 repeats, 58 channels):** XGBoost PR-AUC 0.589 +/- 0.125, F1 0.50; logistic regression PR-AUC 0.599 +/- 0.091, F1 0.54; majority baseline PR-AUC 0.312, F1 0. There is real signal on unseen channels (about double the baseline PR-AUC), but it is modest and noisy, and XGBoost has no edge over logistic regression.
- **The first numbers were inflated by channel leakage:** on by-video splits XGBoost scored PR-AUC 0.981 val / 0.995 test (F1 0.91 / 0.90); the same model in by-video k-fold scores 0.989. Do not quote those. Details: `docs/writeups/phase-3/real-data-first-run.md` and `docs/writeups/phase-3/cross-validation.md`.
- Not yet done: `slop model ablation` (metadata vs +text vs +vision, ideally under channel-grouped CV), scaling the logistic regression's features (it hits its iteration limit), tuning the decision threshold, the SHAP report (item 13), promoting a model to active (item 15), and anything AWS. More labeled channels would help most: there are effectively only 58 labeled examples.

- Reminder: the CLI imports torch/prefect at startup, so each `slop` command takes about a minute to start, and NLP scoring of ~42k comments on CPU took over two hours. Run long commands in the background, and keep an eye on memory - one retrain was killed by the OS's low-memory protection and had to be re-run.
- `uv run slop model train --model both`, then `uv run slop model evaluate --model-name <name> --model-version <version> --split val` (and `--split test`), then `uv run slop model report --model-name <name> --model-version <version> --split test`.
- **Verify with:** `docs/writeups/phase-3/stage-7-model-training.md`, `stage-8-evaluation.md`, `stage-9-error-analysis.md`, and the `phase-3-overview.md`'s closing checklist. These docs already show what real output looks like on synthetic data - your real run should follow the same shape, but the actual numbers (does it beat the majority baseline "convincingly"?) are the qualitative judgment call the roadmap leaves to you.

---

## Optional now

### 8. Set up Weights & Biases (W&B) tracking

**Status: not done, but not blocking** - `.env`'s `WANDB_API_KEY` is blank, and training works completely normally without it (this was a deliberate design decision, not an oversight).

- Sign up for a free account at https://wandb.ai, get your API key from https://wandb.ai/authorize.
- Set `WANDB_API_KEY` (and optionally `WANDB_PROJECT`, defaults to `slop-or-not`) in `.env`.
- **Verify with:** `docs/writeups/phase-3/stage-1-ml-dependencies.md` (confirms the `wandb` package imports cleanly) and `stage-7-model-training.md` (explains the best-effort wrapper: with no key, `slop model train` logs "WANDB_API_KEY not set - skipping W&B tracking" at info level and continues normally; with a key set, run `slop model train` and check https://wandb.ai/&lt;your-username&gt;/slop-or-not for a logged run with `train_rows`/`scored_rows` metrics).
- If you skip this entirely, nothing breaks - it's confirmed optional by both the design and a unit test that mocks a W&B failure and proves training doesn't crash.

### 9. HuggingFace model checkpoint downloads (Phase 4)

**Status: done** - all 3 checkpoints downloaded and verified: `sentence-transformers/all-MiniLM-L6-v2` (~90MB, Stage 3), `cardiffnlp/twitter-roberta-base-sentiment-latest` (~500MB, Stage 5), `openai/clip-vit-base-patch32` (~600MB, Stage 8).
- Cached under `~/.cache/huggingface` afterward - no further network needed once downloaded, even offline.
- **Windows-specific, harmless**: `huggingface_hub` warns on first download that it can't use symlinks for its cache on this machine (no Developer Mode/admin), so cached files are stored as full copies instead - uses a bit more disk space, no effect on correctness. Ignorable, or silence it by setting `HF_HUB_DISABLE_SYMLINKS_WARNING=1` if it's annoying.
- Nothing to do right now - this just needs a working internet connection whenever you first run those commands, not an account or API key.
- **Verify with:** `docs/writeups/phase-4/stage-3-embeddings-wrapper.md` (done) and later stage docs for sentiment/CLIP - each documents a `@pytest.mark.slow` test you can run manually (`uv run pytest -m slow`) to confirm a given model downloads and produces sane output, separate from the fast default test suite.

### 10. CPU-only PyTorch - confirmed working

**Status: done** - verified in `docs/writeups/phase-4/stage-1-ml-dependencies.md`. `torch` installed as `torch==2.14.0+cpu` (118MB, not the multi-GB CUDA build) and `torch.cuda.is_available()` returns `False`. Nothing further to do here; recorded so the decision (CPU-only, confirmed with you before implementation) and its verification are both traceable in one place.

### 11. Disk space for Phase 4's dependencies

**Status: informational, not an action item.** Phase 4's dependency + model-cache footprint (~2-3GB combined: CPU-only torch + transformers + sentence-transformers + the 3 cached checkpoints from item 9) is much larger than Phase 3's near-zero footprint. Worth knowing if you're on a constrained machine, but nothing to set up.

### 12. Keep Docker Desktop actually running

**Status: operational reminder, not a one-time setup step.** While verifying Phase 4 Stage 1, Docker Desktop had stopped running in the background (the Windows `com.docker.service` service was stopped) and every DB-touching test hung indefinitely instead of failing fast, since the connection attempt sat waiting on a port nothing was listening on. This isn't a code bug - it just looks exactly like one if you don't check Docker first.
- If `uv run pytest` (or `slop smoke`, or anything else touching Postgres/MinIO) seems to hang rather than error, check `docker compose ps` first - if it errors instead of listing containers, Docker Desktop itself isn't running, not just the containers.
- **Verify with:** `docs/writeups/phase-4/stage-1-ml-dependencies.md`, which documents exactly this diagnosis (ran `pytest -v` with a hard timeout to see which test it stuck on, confirmed via `docker compose ps` and `Get-Service com.docker.service`).

### 13. Run the SHAP interaction report (Phase 4, Stage 14)

**Status: blocked on item 7 (needs a real trained "all features" model) - not automated, run manually.**

- Once a real `xgboost_all` model exists (from `slop model ablation --model xgboost --split val` or a plain `slop model train`, over real labeled data): `uv run python scripts/shap_interaction_report.py <path to model.joblib> --splits-csv data/splits.csv --split test`.
- This is deliberately a standalone script, not a `slop` subcommand - a one-off analysis artifact for the README, not something you'd run routinely.
- Only works against a tree-based estimator (`xgboost`), not `logistic_regression` - `shap.TreeExplainer` doesn't support the latter.
- **Verify with:** `docs/writeups/phase-4/stage-14-shap-interaction-report.md` - explains the CSV's columns (feature names are post-one-hot-encoding, so a categorical interaction shows up as one row per category) and the caveats around multi-class interaction-value shapes.

### 15. Promote a trained model to active (Phase 5)

**Status: not done, but not blocking** - `.env`'s `ACTIVE_MODEL_NAME`/`ACTIVE_MODEL_VERSION` are blank, and the API works completely normally without them (returns `score: null`/`predicted_label: null` on every video, which is expected/correct until a real model exists).

- Once a real model has been trained (item 7, or `slop model ablation`) and you've decided which one should be "the" model shown by default: set `ACTIVE_MODEL_NAME`/`ACTIVE_MODEL_VERSION` in `.env` to that model's exact `model_name`/`model_version` (as printed by `slop model train`/`ablation`, or queryable via `SELECT DISTINCT model_name, model_version FROM video_scores`).
- `GET /videos` and `GET /videos/{id}` both still accept `model_name`/`model_version` query params to override this on a per-request basis (useful for comparing ablation variants without changing `.env`).
- **Verify with:** `docs/writeups/phase-5/stage-5-videos-router.md` and `stage-8-active-model-config.md` - set the env vars, restart `uvicorn`, confirm `GET /videos` returns non-null scores for videos that have a `video_scores` row under that exact model name/version.

### 16. Node.js/npm for the React frontend (Phase 6)

**Status: done on this machine** - `node` v24.13.0 and `npm` v11.17.0 confirmed installed and on `PATH` (checked directly, not assumed). Nothing to do here unless setting up a fresh machine.

- On a machine without it: install Node.js (LTS or current - this project was scaffolded against Node 24) from https://nodejs.org, which bundles `npm`.
- All frontend dependencies live in `web/package.json`/`web/package-lock.json` (a separate lockfile from the backend's `uv.lock`) - run `npm install` inside `web/` once, not at the repo root.
- **Windows-specific, real issue found and fixed**: Vitest's default `forks` test-runner pool timed out starting worker processes on this Node/Windows combination ("Failed to start forks worker" / "Timeout waiting for worker to respond") - fixed by setting `test.pool: 'threads'` in `web/vite.config.ts`. If tests hang or fail to start on a different machine, check this first before assuming a real test failure.
- **Verify with:** `docs/writeups/phase-6/stage-3-frontend-scaffolding.md` - `cd web && npm install && npm run build && npx vitest run && npm run lint`, all of which should pass cleanly.

### 17. Prefect server + scheduled `serve` process (Phase 7)

**Status: server confirmed running via docker-compose; the scheduled refresh needs a `slop orchestrate serve` process left running whenever you want it to actually fire.**

- `docker compose up -d prefect-server` brings up Prefect's own orchestration API + UI at http://localhost:4200 (self-contained - its own SQLite store for flow-run history/deployments, not sharing the app's Postgres). Confirmed healthy and reachable in Stage 1 (`curl http://localhost:4200/api/health` -> `true`).
- The server container does NOT run your flow code - it's just the API/UI. Actually executing flows (ingest/features/scoring, which need the full `sloppy` package + torch/transformers) happens via **`uv run slop orchestrate serve`, run on the host and left running** (its own terminal, or a background service) - unlike a typical Prefect work-pool setup, this project uses `flow.serve()` (Stage 6), which needs no separate work pool or worker process; the `serve` command itself both registers the daily cron schedule and executes runs against it. Without that process running, the schedule still exists in the server (confirmed via `docker compose up -d prefect-server` alone), but every scheduled or manually-triggered run just sits in a "Scheduled"/"Late" state and never executes.
- Every `uv run prefect ...`/`uv run slop orchestrate ...` command needs `PREFECT_API_URL` set in that shell first, or it talks to a throwaway ephemeral server instead of the docker-compose one - easy to forget and confusing when flow runs "disappear." (`uv run prefect config set PREFECT_API_URL=...`, done once in Stage 1, persists this across shells too.)
- **Verify with:** `docs/writeups/phase-7/stage-1-prefect-server.md` for the server; `stage-6-scheduled-deployment.md` for the real registered deployment/schedule; later Phase 7 stage docs for how a flow run's actual execution (and a forced retry) were confirmed, both in the terminal and in the UI at http://localhost:4200.

### 18. Provision the real AWS deployment (Phase 8)

**Status: not done, but not blocking** - the app is fully built and tested locally (Docker Compose); this is the actual "go live" step, entirely manual, entirely optional until you want a public URL. Phase 8's code/config side (AWS-compatible `Settings`, a production `web`+`api` docker-compose path, and real reference Terraform) is done - see `docs/writeups/phase-8/`. **No AWS account, credentials, or billable resources exist anywhere yet** - confirmed directly before Phase 8 was built.

- Create an AWS account if you don't have one, then create an IAM user (or role, if you're using AWS SSO/Identity Center) with least-privilege permissions for the resources below - never use root credentials day to day. Install the AWS CLI and run `aws configure` (or set `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/`AWS_DEFAULT_REGION` env vars) so Terraform can authenticate.
- Review and customize `infra/terraform/variables.tf` before ever applying: `thumbnails_bucket_name` (must be globally unique across all of AWS - the default is a deliberate placeholder), `db_password` (pass via `TF_VAR_db_password`, never a literal default), `ssh_ingress_cidr` (your own IP/32, never left at its non-functional placeholder default).
- `cd infra/terraform && terraform init && terraform plan && terraform apply` - this is the one step in this entire project that costs real money and creates real, billable resources. Review the plan output carefully before typing `yes`.
- **Manual, post-apply, SQL-level step Terraform can't do**: connect to the new RDS instance and run `CREATE EXTENSION IF NOT EXISTS vector;` - pgvector is a Postgres extension enabled per-database, not an AWS resource.
- Update `.env` per `infra/terraform/README.md`'s mapping table (RDS endpoint, real bucket name, `AWS_REGION`, `POSTGRES_SSLMODE=require`, and leave `S3_ACCESS_KEY`/`S3_SECRET_KEY` **unset** so the EC2 instance's IAM role is used instead of long-lived keys), then SSH into the instance, install Docker, clone the repo, and run `docker compose up -d --build api web`.
- Optional follow-ups, not required for the roadmap's "public URL serves the dashboard end-to-end" verify bullet: a real domain + TLS certificate (the EC2 instance's plain public IP over HTTP is enough for a first pass), moving the frontend to S3+CloudFront instead of the EC2-hosted nginx container (the roadmap's own "optionally" alternative).
- **Verify with:** `docs/writeups/phase-8/` (all stages) and `infra/terraform/README.md` for the exact resource-to-`.env` mapping; once deployed, the roadmap's own verify bullet - load the public URL in a browser and confirm the dashboard works end to end, the same checks Phase 8 Stage 2 ran locally against `http://localhost:8080`.

### 19. Confirm raw comment text is never exposed publicly (Phase 8 / cross-cutting)

**Status: already satisfied by design, documented here for the record.** `ROADMAP.md`'s cross-cutting notes say explicitly: "Don't publish raw comment text in the public demo - store it, show aggregates." Checked directly while writing Phase 8: no API schema in `src/sloppy/api/schemas.py` exposes raw `Comment.text` anywhere - only aggregate counts (`comment_count`, `comment_count_scored`) and derived scores (`sentiment_mean`, `slop_keyword_rate`, etc.) ever leave the database via the API. Comment text is read internally (for sentiment scoring and embeddings, Phase 4) and never returned to a client.

- Nothing to do here - flagged so this constraint stays visible and gets re-checked if a future endpoint is ever added that touches `Comment` rows.
- **Verify with:** `grep -n "comment" src/sloppy/api/schemas.py` - every match should be a count or a derived score, never `text`.

### 20. CLI progress spinner (dev tooling, 2026-10-05)

**Status: informational, nothing to set up.** Long commands (`ingest seed-channels`, `ingest channel`, `ingest trim-all`, `features compute-nlp`/`compute-vision`) show a single-line spinner via `src/sloppy/cli_ui.py`, with `[ok]`/`[warn]`/`[FAIL]`/`[skip]` result lines printed above it. It uses `rich`, which turns the live line off when output is not a terminal. Under Git Bash the shell hands Python a pipe, so the spinner is forced on when `MSYSTEM` and `TERM` are set; set `SLOP_PLAIN=1` to switch it off (do this when redirecting output to a log file, otherwise the log fills with spinner frames). Terminals whose output encoding cannot show braille characters (for example cp1252) get an ASCII spinner; set `PYTHONIOENCODING=utf-8` for the nicer one. This was written but only verified against its unit tests and a piped demo, not yet watched in an interactive terminal.

---

## How to keep this list current

Update this file whenever a phase's writeups reveal a new external dependency (an account, a paid service, a manual data step) - the pattern so far is one section per external thing, with a status line and a pointer to whichever stage writeup(s) show the real "did I do this right" check. When an item above gets done, change its **Status** line rather than deleting the section, so the history of what was manual vs. automated stays visible.
