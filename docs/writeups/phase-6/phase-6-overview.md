# Phase 6 - React dashboard (full write-up)

This covers the whole of Phase 6 end-to-end. For stage-by-stage detail, see `stage-1-channel-detail-endpoint.md` through `stage-10-labeling-page.md` in this same directory.

## What is being implemented

The first UI for this project - a Vite + React + TypeScript + Tailwind + TanStack Query dashboard in `web/` (the directory Phase 0 reserved for it), consuming every endpoint Phase 5 built plus two small backend additions this phase needed. Four pages: a paginated/sortable/filterable video grid (with an "ingest a channel" entry point), a video detail page (full feature breakdown + similar-video strip), a channel view (stats + that channel's own video grid), and a labeling page that replaces the CLI's `slop label run`.

Built across eleven stages:

1. **`GET /channels/{id}`** (`src/sloppy/api/routers/channels.py`) - a genuine backend gap found during planning: `GET /videos` never returns channel-level stats.
2. **`GET /labels/pool`** (added to `src/sloppy/api/routers/labels.py`) - exposes Phase 2's `candidate_videos`/`sample_pool`/`consistency_sample` over HTTP, so the web labeling page gets the same per-channel-max/corpus-shape guarantees the CLI already had.
3. **Frontend scaffolding** (`web/`) - Vite + React 19 + TypeScript 6 (strict) + Tailwind v4 + Vitest + React Testing Library + MSW, plus a dev-server proxy (`/api/* -> :8000/*`) so the backend never needed CORS middleware.
4. **API client layer** (`web/src/api/`) - hand-written TypeScript types mirroring every Pydantic schema, a thin `fetch` wrapper, and TanStack Query hooks.
5. **Routing shell** (`web/src/routes.tsx`, `Layout.tsx`) - 4 real routes + a not-found catch-all, structured so tests use `MemoryRouter` instead of `BrowserRouter`.
6. **Video grid page** - `ScoreBadge`, `VideoCard`, sort/order/filter controls, pagination.
7. **Video detail page** - full metadata, NLP/vision feature breakdowns, similar-video strip.
8. **Channel view page** - channel stats header + that channel's video grid, sharing Stage 6's grid/controls via a `useVideoListState` hook extracted for reuse.
9. **Ingest-trigger UI** - a form on the video grid page calling `POST /ingest`, with an honestly-vague success message given the backend's fire-and-forget design.
10. **Labeling page** - fetches a pool once, walks through it with `y`/`n`/`s` keyboard shortcuts mirroring the CLI exactly, persists a labeler name to `localStorage`.
11. **Full demo-path verification** (this stage) + this overview.

## Architecture, end to end

```
Browser
   |
React app (web/, Vite dev server on :5173)
   |
   +-- VideoGridPage --- useVideos() ------------> GET /api/videos -----\
   |     + IngestForm -- useCreateIngest() ------> POST /api/ingest      \
   |                                                                      \
   +-- VideoDetailPage - useVideoDetail() -------> GET /api/videos/{id}   |
   |                                                                       > Vite dev proxy
   +-- ChannelViewPage - useChannel() + useVideos()> GET /api/channels/{id}| rewrites /api/*
   |                                                  GET /api/videos      | to :8000/*
   |                                                                      /
   +-- LabelingPage --- useLabelPool() -----------> GET /api/labels/pool /
                       useCreateLabel() ----------> POST /api/labels    /
                                                                       /
                                            FastAPI (uvicorn on :8000)
                                                       |
                                     same routers/session_scope()/pgvector
                                     queries built in Phases 4-5, plus the
                                     2 new endpoints from Stages 1-2 above
```

Every page follows the same shape: a TanStack Query hook (Stage 4) supplies `data`/`isLoading`/`isError`, the component renders a loading/error/empty state or the real content, and any write action (`POST /labels`, `POST /ingest`) goes through a mutation hook. No component calls `fetch` directly - everything funnels through `web/src/api/`.

## What it should look like

Verified for real against the live backend with genuinely seeded (synthetic) data in Stage 11 - not just MSW mocks:

```
$ curl http://localhost:5173/api/videos
{"items":[{"id":"demo_phase6_video", "title":"Demo Phase 6 Video", ..., "score":null, ...}],
 "total":1, "limit":20, "offset":0}

$ curl http://localhost:5173/api/videos/demo_phase6_video?model_name=demo_model&model_version=v1
{"id":"demo_phase6_video", ..., "score":0.42, "predicted_label":"up", ...}

$ curl http://localhost:5173/api/channels/UC_demo_phase6
{"id":"UC_demo_phase6", "title":"Demo Phase 6 Channel", "subscriber_count":5000, ...}

$ curl -X POST http://localhost:5173/api/labels -d '{"video_id":"demo_phase6_video","labeler":"e2e-check","label":"up"}'
{"video_id":"demo_phase6_video", "labeler":"e2e-check", "label":"up", ...}

$ curl -X POST http://localhost:5173/api/ingest -d '{"channel":"@fake-channel-for-e2e-check"}'
{"status":"accepted", "target":"@fake-channel-for-e2e-check"}
```

All 5 requests went through the real Vite dev proxy to the real FastAPI backend against the real dev Postgres, with data inserted via the actual `upsert_channel`/`upsert_video`/`upsert_video_score` helpers and cleaned up afterward (confirmed empty via a follow-up `GET /videos`). This is the strongest verification available without real YouTube data - the full request path (browser-facing proxy -> FastAPI router -> SQLAlchemy query -> response) was exercised exactly as a real user's browser would exercise it.

## What to look out for

**A real bug pattern that recurred 4 times across this phase, each time caught and fixed**: whenever a Stage 5 placeholder page was replaced by a real, data-fetching page (Stages 6, 7, 8, 10), the corresponding routing test in `routes.test.tsx` broke - it was still asserting on the placeholder's static text, and once the real page tried to fetch data, MSW's `onUnhandledRequest: 'error'` setup (Stage 3) surfaced the missing mock immediately. Each time, the fix was the same: register an MSW handler for the endpoint that page calls, and switch the assertion from synchronous (`getByText`) to asynchronous (`await screen.findByText`). This is now a known, expected pattern rather than a surprise - worth remembering for any future page added to this app.

**Two other real bugs, each caught by a test failure, not assumed**:
- Stage 4: TypeScript strict mode rejected `buildQuery`'s original `Record<string, ...>` parameter type when called with a named interface (`ListVideosParams` etc.) - "index signature missing." Fixed by typing the parameter as plain `object` and casting internally.
- Stage 6: an error-path test timed out because TanStack Query's default retry-with-backoff pushed the actual error state past React Testing Library's default 1-second `findBy` timeout. Fixed by disabling retries in the test `QueryClient` (`retry: false`), not in production.

**Design decisions worth remembering**:
- Hand-written TypeScript types (not OpenAPI-generated) mirror `src/sloppy/api/schemas.py` field-for-field - a confirmed tradeoff that trades codegen tooling for a manual-sync burden if the backend schemas change.
- `useLabelPool` and the labeling page's pool-walking both deliberately avoid any automatic refetch/reshuffle mid-session (`staleTime: Infinity`), mirroring the CLI's own "fetch once per session" behavior exactly.
- The ingest form's success message is deliberately non-committal ("started... check back in a bit") because Phase 5's `POST /ingest` is genuinely fire-and-forget with no status endpoint - the frontend cannot honestly claim more than that.
- `GET /channels/{id}` and `GET /videos?channel_id=...` are two separate calls on the channel view page, not one combined endpoint - deliberately avoiding duplicating `GET /videos`'s pagination/sort/filter logic inside a new nested-response endpoint.
- No consistency-mode (relabeling spot-check) UI exists yet on the labeling page, even though the backend supports it (`GET /labels/pool?mode=consistency`) - a real, acknowledged gap for a future stage/phase, not hidden by the tests.

**No real ingested/labeled data exists yet anywhere in this environment** - same running theme as every prior phase. Every stage's automated tests used MSW-mocked or synthetic-but-real backend data; Stage 11's final check used genuinely seeded (then cleaned up) synthetic rows through the real, live backend to prove the whole path works, but whether the actual pages look right against hundreds of real videos and thumbnails is still deferred to real data, tracked in `docs/writeups/TODO.md`.

## How to run tests properly

```powershell
# Backend
uv run pytest                    # 158 passed, 5 deselected
uv run ruff check .
uv run ruff format --check .

# Frontend
cd web
npm install                      # first time only
npx tsc -b
npx vitest run                   # 11 files, 52 tests
npm run lint
npm run build

# Full manual demo path (both servers)
uv run uvicorn sloppy.api.app:app --port 8000     # from repo root
npm run dev                                        # from web/, proxies /api to :8000
# open http://localhost:5173 - paste a channel into the ingest form, browse the grid,
# click into a video, click into its channel, try the labeling page
```

## What's next

Phase 6's code is complete; the remaining work is entirely about real data (still blocked on Phase 2's curation/labeling per `docs/writeups/TODO.md`) and eventually running the real demo path against it. Per `ROADMAP.md`, Phase 7 (Prefect orchestration) is next: wrapping ingest -> features -> score as a scheduled, retryable flow - which will directly replace this phase's `POST /ingest` `BackgroundTasks` placeholder with something that actually tracks job state, closing the "no status, no push notification" gap this phase's `IngestForm` had to work around honestly rather than paper over.
