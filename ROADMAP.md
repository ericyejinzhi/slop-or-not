# Slop-or-Not: Tech Stack & Phased Roadmap

> YouTube content-quality classifier ("slop or not") using video metadata, comments,
> thumbnails, channel sentiment, and cross-video similarity.

## Project decisions

- **Labels**: manual labeling (~300–500 videos, hand-labeled against a written rubric)
- **Frontend**: React + FastAPI (accepting the JS learning curve for portfolio value)
- **Deployment**: Docker Compose locally first, migrate to AWS in a late phase
- **Goal**: learning and portfolio weighted equally - industry-standard tools, but sequenced so there's always a working end-to-end system
- **Assumed skill level**: fluent in Python, novice with everything else

## Recommended stack (with rationale)

| Layer | Choice | Why this over alternatives |
|---|---|---|
| Language/tooling | Python 3.12, **uv** (env + deps), ruff, pytest | uv is the modern standard - one tool instead of pip + venv + pip-tools |
| Ingestion | **google-api-python-client** (YouTube Data API v3) + **yt-dlp** | API for metadata/comments (quota-cheap), yt-dlp for thumbnails |
| Database | **PostgreSQL 16 + pgvector** (Docker) | pgvector kills the need for FAISS - one system for metadata AND vector similarity. FAISS only if scale demands it later (it won't at <100k videos) |
| ORM/migrations | **SQLAlchemy 2.x + Alembic** | Industry standard, transferable skill |
| Object storage | **MinIO** (Docker, S3-compatible) | Code uses boto3 against MinIO locally; AWS migration = change endpoint env var |
| Sentiment | **HuggingFace Transformers**, pretrained (e.g. `cardiffnlp/twitter-roberta-base-sentiment-latest`) | No training needed; YouTube comments ≈ tweets in register |
| Text embeddings | **sentence-transformers** (`all-MiniLM-L6-v2` to start) | Small, fast, CPU-friendly |
| Thumbnails | **CLIP embeddings** (via `open_clip` or HF) + linear probe | Embedding + logistic regression beats training a CNN from scratch on a few hundred labels; zero-shot prompts ("a clickbait thumbnail") as bonus features |
| Fusion classifier | **scikit-learn / XGBoost** over engineered features + embeddings | Right-sized for ~500 labels; deep fusion would overfit |
| Experiment tracking | **Weights & Biases** (free tier) | Zero infra vs MLflow (which needs another server to run); swap later if desired |
| Orchestration | Plain Python CLI (**typer**) first → **Prefect** in Phase 7 | Airflow is heavy ops overkill for one person; Prefect is pip-installable and decorator-based |
| API | **FastAPI** + pydantic | Modern standard, auto-generated OpenAPI docs |
| Frontend | **React + TypeScript + Vite**, Tailwind, TanStack Query | Standard modern stack; Vite for zero-config dev |
| Config | **pydantic-settings** + `.env` | 12-factor from day one → painless AWS move |

## Architecture

```
YouTube API / yt-dlp
        │
   ingest CLI (typer)  ──►  Postgres + pgvector (metadata, comments, labels, embeddings, scores)
        │                        ▲
        └──► MinIO (thumbnails)  │
                                 │
   feature/scoring pipeline ─────┘   (sentiment, embeddings, fusion model)
                                 │
        FastAPI  ◄───────────────┘
           │
        React dashboard (scores, similar videos, labeling UI)
```

## Phases

Each phase ends with something demoable. Rough effort assumes part-time work.

### Phase 0 - Scaffolding (a weekend)

- `git init`; repo layout: `src/sloppy/` package (`ingest/`, `features/`, `models/`, `api/`), `web/` for React later, `docker/`, `tests/`
- uv project, ruff, pytest, pre-commit
- `docker-compose.yml`: `postgres` (pgvector/pgvector image), `minio`
- pydantic-settings config, `.env.example`; get a YouTube API key (free, 10,000 units/day)
- **Verify**: `docker compose up`, connect to Postgres from Python, put/get a file in MinIO with boto3.

### Phase 1 - Ingestion (1–2 weeks)

- SQLAlchemy models + Alembic migration: `channels`, `videos`, `comments`, `thumbnails`
- YouTube client: fetch channel → uploads playlist → video metadata → top ~100 comments per video
  - Request `part=snippet,statistics,contentDetails,topicDetails` on `videos.list`: `contentDetails.duration` gives video length, `topicDetails.topicCategories` gives Wikipedia-based genre tags (Documentary, Gaming, …). Note: the comment-section "Topics" chips in the YouTube UI are **not** exposed by the Data API - genre comes from `topicDetails`, and comment-topic condensation is done ourselves in Phase 4
  - **Quota note**: use `playlistItems.list` (1 unit) not `search.list` (100 units); comment threads are 1 unit/page
- yt-dlp thumbnail download → MinIO, keyed by video id
- `slop ingest channel <id|handle>` CLI; idempotent (re-runs upsert)
- **Verify**: ingest 3–5 channels (~200+ videos), row counts sane, thumbnails visible in MinIO console.

### Phase 2 - Rubric & labeling (1 week)

- Write `docs/rubric.md`: an explicit definition of slop (e.g. mass-produced/templated, misleading thumbnail–title mismatch, low-information content) with examples. This doc is the intellectual core of the project - great README material
- `labels` table (label, labeler, timestamp, notes) + a **keyboard-driven labeling CLI** (shows title/thumbnail path/stats). Don't block on React for this; a labeling page can join the dashboard in Phase 6
- **Labeling scheme: thumbs up / thumbs down / skip** (one keystroke each). Binary keeps you consistent across sessions and matches the binary classifier downstream; with only a few hundred labels, a 1–5 scale spreads data thin and grade calibration drifts. *Optional nuance*: store a 0–3 slop-severity score in the same table and binarize it for training - decide after the first ~50 labels whether the extra grade feels reliable
- No sub-labels (title intent, etc.) - title analysis is handled unsupervised in Phase 4
- **Corpus shape: wide and moderately shallow** - ~40–80 channels × their ~15–30 most recent uploads, not a handful of channels × full backlog. Few channels deep = the model fingerprints channels instead of learning slop, and channel-grouped eval becomes unreliable with few groups; but keep ≥15 videos per channel so channel-level features (cadence, duration norms, templated-ness) stay computable. Recent uploads only - channels drift/pivot
- **Channel selection rules**: (1) pair within genre - every genre gets slop AND quality AND ambiguous channels, so genre can't become a proxy for the label; (2) include the boring mid-tier, not just famous slop farms vs. beloved creators. Maintain a hand-curated `data/seed_channels.csv` (handle, expected-lean, genre, source-of-discovery) instead of burning `search.list` quota (100 units/call) on discovery
- Label a sampled subset of 300–500 videos from the ingested corpus
- **Labeling unit: per-video, in shuffled order across channels** - never channel-by-channel. Channel-level labels reduce the whole project to a channel classifier, and labeling a channel's videos consecutively anchors you to its reputation instead of the video in front of you (so the labeling CLI shuffles). The disagreements - a quality creator's lazy upload, a slop farm's decent one - are the most informative labels in the set. Channel-level intuition lives only in `seed_channels.csv`'s expected-lean column (corpus balance + sanity checks), never as training ground truth
- Stratified train/val/test split, **grouped by channel** - never let one channel's videos span train and test, or the model will just memorize channels
- **Verify**: label distribution isn't degenerate (aim ≥25% minority class); spot-check consistency by relabeling 20 videos a week later.

### Phase 3 - Baseline model (1 week)

- Feature engineering from metadata alone: title stats (caps ratio, emoji count, clickbait n-grams), channel upload cadence, like/view and comment/view ratios, description length, tag count
- **Video length features**: raw duration, duration bucket (short/mid/long-form), and - the useful one - *deviation from the norm for the video's genre* (`topicDetails`) and for its own channel. 45 seconds is normal for Shorts, suspicious for a "documentary"
- Genre (`topicDetails`) enters as a categorical feature, so every other feature is implicitly conditioned on it by the tree model
- Logistic regression + XGBoost via scikit-learn; metrics: PR-AUC, F1, confusion matrix (report per-channel to catch leakage)
- W&B run tracking; persist model artifact + a `video_scores` table
- **Verify**: beats majority-class baseline convincingly; error-analysis notebook of top false positives/negatives.

### Phase 4 - NLP + vision features (2–3 weeks, the ML heart)

- **Comment sentiment**: pretrained transformer over comments → per-video aggregates (mean/std sentiment, % negative, "AI slop"/"bot" keyword rates); roll up to channel-level sentiment
- **Comment topic condensation** (our stand-in for the UI-only "Topics" chips): cluster the per-comment embeddings (KMeans, or BERTopic once comfortable) → features like number of distinct topics, share of comments in the top cluster, and per-cluster sentiment. Slop tends to draw a narrow, repetitive comment distribution; genuine content spreads across topics
  - *Decided against scraping the UI Topics chips* (InnerTube or Playwright): experiment-gated so coverage is spotty, schema is undocumented/unstable, and it widens ToS exposure - our own clustering gives the same signal with full coverage. **Parked idea**: scrape chips for ~50 chip-bearing videos later as a one-off validation set to sanity-check our clusters against YouTube's
- **Title intent, unsupervised**: embed each title and score cosine similarity against small hand-written prototype sets for `grey-area lure` ("you won't believe what happened", "this changes everything…"), `intentionally mysterious` ("The Man Who Vanished Twice" - documentary-style withholding that doesn't overpromise), and `transparent` ("How to replace a bike chain"). Plus structural cues: curiosity-gap phrases, unresolved pronouns ("this", "her secret"), ALL-CAPS spans, ellipses. The three similarity scores go in as features rather than a hard classification - the fusion model learns where the boundary sits per genre
- **Text embeddings**: sentence-transformers on title + description (and mean comment embedding) → pgvector columns
- **Thumbnail embeddings**: CLIP image encoder → pgvector; plus zero-shot CLIP scores against prompt sets ("clickbait", "AI-generated image", …) as scalar features
- **Cross-video similarity**: pgvector cosine search → features like "mean distance to channel's own videos" (templated-ness) and "# near-duplicate thumbnails across corpus" - this is the novel signal
- **Feature interactions**: the same signal means different things in combination - a mysterious title on a 90-minute documentary is craft, on a 4-minute video with a lure-scored thumbnail it's bait. XGBoost learns interactions natively (a key reason it's the fusion model), but seed it with explicit crosses where we know the story: `lure-title score × genre`, `duration-vs-genre deviation × upload cadence`, `mysterious-title score × duration bucket`. Check learned interactions with SHAP interaction values for the README
- Retrain fusion model on all features; ablation table (metadata only vs +text vs +vision) for the README
- **Verify**: measurable lift over the Phase 3 baseline in W&B; similarity sanity checks (a video's nearest neighbors look right).

### Phase 5 - FastAPI service (1 week)

- Endpoints: `GET /videos` (paginated, scores), `GET /videos/{id}` (score + feature breakdown + similar videos), `POST /ingest` (queue a channel/video), `POST /labels`
- Serve thumbnails via presigned MinIO URLs; pydantic response schemas; pytest + httpx tests
- Add API container to docker-compose
- **Verify**: OpenAPI docs at `/docs` exercise every endpoint against real data.

### Phase 6 - React dashboard (2–3 weeks, main JS learning curve)

- Vite + React + TS + Tailwind + TanStack Query
- Pages: video grid (thumbnail, score badge, sort/filter), video detail (score breakdown, sentiment, similar-video strip), channel view, labeling page (replaces the CLI)
- **Verify**: full demo path - paste a channel, ingest, watch scores appear, click through to similar videos.

### Phase 7 - Orchestration with Prefect (1 week)

- Wrap ingest → features → score as a Prefect flow with retries/logging; schedule daily refresh of tracked channels; flow-run UI via local Prefect server
- **Verify**: scheduled run completes unattended; a forced API failure retries and surfaces in the UI.

### Phase 8 - AWS migration + polish (1–2 weeks)

- MinIO → S3 (endpoint/creds env change); Postgres → RDS (pgvector supported) or Dockerized Postgres on the instance; API + frontend → single EC2 with docker-compose (simplest) or ECS if feeling ambitious; frontend optionally to S3 + CloudFront
- README with architecture diagram, rubric summary, ablation results, demo GIF
- **Verify**: public URL serves the dashboard end-to-end.

## Cross-cutting notes

- **Quota/ToS**: 10k units/day is plenty for metadata + comments at this scale; yt-dlp only for thumbnails (don't archive video/audio). Don't publish raw comment text in the public demo - store it, show aggregates.
- **GPU not required**: all models run fine on CPU at this scale; batch-embedding a few thousand items is minutes, not hours.
- **Always shippable**: Phases 1–3 already constitute a complete "data pipeline + baseline model" story if momentum stalls.
