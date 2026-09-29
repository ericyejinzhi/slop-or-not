# Phase 6, Stage 6 - Video grid page

## What is being implemented

The first real page, replacing Stage 5's placeholder at `/`: a paginated, sortable, filterable grid of videos backed by `GET /videos`.

- `web/src/components/ScoreBadge.tsx` - a small pure component: "Unscored" (grey) when `score`/`predictedLabel` are `null`, otherwise the label + score to 2 decimal places, colored red for `down` and green for `up`.
- `web/src/components/VideoCard.tsx` - a thumbnail (or a "No thumbnail" placeholder box when `thumbnail_url` is `null`), title, channel handle, `ScoreBadge`, and view count, wrapped in a `Link` to `/videos/:id` (Stage 7's page).
- `web/src/pages/VideoGridPage.tsx` - owns `sort`/`order`/`predicted_label`/`offset` as local component state, builds a `ListVideosParams` object from it, and calls `useVideos(params)` (Stage 4's hook). Renders sort/order/filter `<select>`s, the card grid, a "no videos match" message when the result is empty, and Previous/Next pagination buttons (disabled at the start/end of the result set, computed from `total`/`limit`/`offset`).

Filters and sort reset `offset` back to `0` when changed, so changing "Sort" mid-way through page 3 doesn't leave you looking at page 3 of a completely different result set.

## What it should look like

```
$ curl http://localhost:8000/videos
{"items": [], "total": 0, "limit": 20, "offset": 0}
```

confirmed reachable and shape-correct against the real (currently empty) dev backend during this stage's verification - real visual rendering against actual videos is deferred, same as every prior phase, since no real ingested data exists yet.

The real verification for rendering behavior is the automated test suite: `web/src/pages/VideoGridPage.test.tsx` (6 tests) uses MSW to serve realistic `VideoListResponse` payloads and asserts the rendered DOM directly - a video's title/channel handle/score badge/view count all appear correctly formatted; an empty result shows the "no videos match" message; a 500 response shows "Failed to load videos"; clicking "Next" issues a request with `offset=20`; "Previous" is disabled on the first page; changing the filter dropdown issues a request with `predicted_label=down`.

## What to look out for

- **A real timing bug found and fixed, not a design choice**: the "shows an error message when the request fails" test initially timed out waiting for "Failed to load videos" to appear, still showing "Loading videos..." after 1 second. The `createQueryClient()` factory's production default (`retry: 1`) means a failing query retries once before settling into its error state - and TanStack Query's default retry delay (exponential backoff starting around 1 second) pushed the actual error state past React Testing Library's default `findBy` timeout of 1000ms. Fixed by giving `createQueryClient` an optional `retry` override and having the test wrapper (`src/test/queryClientWrapper.tsx`) pass `retry: false` - tests shouldn't wait through real network-retry delays regardless of what the production app does. Worth remembering for any future error-path test: if a `findBy` assertion mysteriously times out on an error case that clearly did happen, check whether query retries are the reason before assuming the component is broken.
- **Two pre-existing tests broke when the real page replaced the Stage 5 placeholder, and needed fixing, not the new page**: `routes.test.tsx`'s "/" test and `App.test.tsx` both previously asserted on the placeholder's static text ("Video grid coming in Stage 6"). Once `VideoGridPage` became a real, data-fetching component, both tests started hitting MSW's `onUnhandledRequest: 'error'` (no handler existed for `/api/videos` in those test files) and needed a mock handler plus an `await screen.findByText(...)` (the real page renders asynchronously; the placeholder didn't). This is an expected, recurring pattern for the rest of Phase 6 - Stages 7 and 8 will need the same fix applied to their own routing-test assertions once `VideoDetailPage`/`ChannelViewPage` stop being placeholders.
- **Pagination and filter state live in plain `useState`, not the URL** (no query-string syncing) - a deliberate simplification for this phase: reloading the page or sharing a link always lands back on page 1 with no filters. Revisiting this (e.g. with `useSearchParams`) is a reasonable future improvement, not attempted here.
- `VideoCard`'s thumbnail `<img>` has no `onError` fallback if a presigned URL happens to be expired/broken when rendered - out of scope for this stage, worth reconsidering once real thumbnails exist and this can actually be observed.

## How to run tests properly

```powershell
cd web
npx tsc -b
npx vitest run        # 6 files, 27 tests
npm run lint
npm run build
```

No backend changes in this stage - `GET /videos` already existed from Phase 5.
