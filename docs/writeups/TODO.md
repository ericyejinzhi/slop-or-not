# External setup TODO

Everything in this list is a manual, external-to-the-codebase step - an account, a credential, or human judgment work (research, labeling) that no amount of code can do for you. Phases 1-3 are fully built and tested with synthetic data, but nothing has been run against real data yet because every item in the "blocking now" section below is still outstanding (confirmed by checking `.env` and `data/` directly while writing this).

For each item: what to do, why it matters, and which writeup(s) tell you exactly how to confirm you did it right - most of them end with "How to verify" pointing at a real command and real expected output already documented from testing that stage.

---

## Blocking now - needed before any of this pipeline touches real data

### 1. Get a YouTube Data API v3 key

**Status: not done** - `.env`'s `YOUTUBE_API_KEY` is blank.

- Go to https://console.cloud.google.com/apis/credentials, create a project if you don't have one, enable "YouTube Data API v3," create an API key (free, 10,000 units/day).
- Paste it into `.env`'s `YOUTUBE_API_KEY=`.
- **Verify with:** `docs/writeups/phase-1/stage-2-youtube-client-metadata.md` and `stage-3-youtube-client-comments.md` - run `slop ingest inspect-channel <a real @handle>` and `slop ingest inspect-video <a real video id>`, cross-check the printed title/stats against the real YouTube page. Those two docs were written specifically because this key wasn't available yet, so they spell out exactly what to check.

### 2. Curate `data/seed_channels.csv`

**Status: not done** - the file exists with only its header row (`handle,expected_lean,genre,source_of_discovery,notes`).

- This is real research, not automatable: pick ~40-80 channels across genres, following `ROADMAP.md`'s channel selection rules - pair quality/slop/ambiguous channels *within* each genre (so genre can't become a proxy for the label), and deliberately include the "boring mid-tier," not just obvious slop farms vs. beloved creators.
- Read `docs/rubric.md` first (Phase 2, Stage 1) - it's the definition of "slop" you'll be implicitly applying when you set each channel's `expected_lean` column.
- Fill in one CSV row per channel: `handle,expected_lean,genre,source_of_discovery,notes`.
- **Verify with:** `docs/writeups/phase-2/stage-3-seed-channels.md` (run `slop label seed-status` after ingesting - see item 3 below - to confirm each channel actually landed in the DB and clears the 15-video floor) and `docs/writeups/phase-2/stage-4-pool-selection.md` (run `slop label pool-preview` to sanity-check genre/channel balance before you start labeling).

### 3. Bulk-ingest the curated channel list

**Status: blocked on items 1 and 2.**

- Once the API key and CSV are in place: `uv run slop ingest seed-channels`.
- **Verify with:** `docs/writeups/phase-1/phase-1-overview.md` (row-count sanity checks via `psql`) and `docs/writeups/phase-2/stage-3-seed-channels.md` (`slop label seed-status` cross-references the CSV against what actually got ingested, and flags any channel under 15 videos).

### 4. Set `LABELER_NAME` in `.env`

**Status: not done** - blank.

- Trivial: put your name (or an initial) in `.env`'s `LABELER_NAME=`. Can also be overridden per-run with `slop label run --labeler <name>` if multiple people ever label.
- **Verify with:** `docs/writeups/phase-2/stage-2-labels-table.md` and `stage-5-labeling-cli.md` - `slop label run` refuses to start with neither set, so successfully starting a session confirms this is wired up.

### 5. Actually label videos

**Status: blocked on items 1-4** - `data/splits.csv` doesn't exist yet because there are zero labels.

- `uv run slop label pool-preview` first (sanity-check corpus shape), then `uv run slop label run --limit 50` (repeat across multiple sessions - the roadmap targets 300-500 labeled videos total).
- Read `docs/rubric.md` before your first session, and expect to revise it after your first ~50 labels once you've seen real edge cases (this is called out explicitly in the rubric itself).
- **Verify with:** `docs/writeups/phase-2/stage-5-labeling-cli.md` (what a session should look like, thumbnail auto-open behavior) and `docs/writeups/phase-2/stage-7-consistency-and-stats.md` (`slop label stats` - check the minority-class share stays above the roadmap's 25% floor as you go).

### 6. Generate the train/val/test split

**Status: blocked on item 5.**

- `uv run slop label make-splits` once you have enough labels.
- **Verify with:** `docs/writeups/phase-2/stage-6-train-val-test-split.md` - confirms no channel spans two splits and that each split's up/down ratio is close to the overall ratio.

### 7. Train and evaluate the baseline model

**Status: blocked on item 6.**

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

---

## Future - not yet built, included so this list stays complete

### 14. AWS account (Phase 8 - "AWS migration + polish")

**Status: not relevant yet** - Phase 8 hasn't been planned or built. Listed here only because you asked for the full external-setup picture, including things like AWS.

- Per `ROADMAP.md`, Phase 8 replaces MinIO with S3, local Postgres with RDS (pgvector-compatible), and runs the API/frontend on EC2 or ECS (optionally CloudFront for the frontend). It will need: an AWS account, an IAM user/role with appropriately scoped permissions (not root credentials), an S3 bucket, an RDS instance, and either an EC2 instance or an ECS cluster.
- No writeup exists yet for this - one will be created following the same pattern (stage-by-stage docs + a phase overview) when Phase 8 is actually planned, which per the roadmap's own sequencing is after Phases 4-7 (NLP/vision features, FastAPI service, React dashboard, Prefect orchestration).
- Nothing to do here right now - don't create AWS resources this early, since Phases 4-7 will change what actually needs to be deployed.

---

## How to keep this list current

Update this file whenever a phase's writeups reveal a new external dependency (an account, a paid service, a manual data step) - the pattern so far is one section per external thing, with a status line and a pointer to whichever stage writeup(s) show the real "did I do this right" check. When an item above gets done, change its **Status** line rather than deleting the section, so the history of what was manual vs. automated stays visible.
