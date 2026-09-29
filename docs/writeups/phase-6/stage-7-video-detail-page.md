# Phase 6, Stage 7 - Video detail page

## What is being implemented

The second real page, replacing Stage 5's placeholder at `/videos/:videoId`: a full breakdown of one video, backed by `GET /videos/{id}`.

- `web/src/lib/format.ts` - three small pure formatting helpers (`formatNumber`, `formatCount`, `formatDate`), all returning `'-'` for `null`/`undefined` rather than `NaN`/`Invalid Date` text - used everywhere a possibly-missing numeric feature is displayed.
- `web/src/components/FeatureList.tsx` - a generic `{label, value}[]` -> two-column `<dl>` renderer, reused for both the NLP and vision feature breakdowns rather than writing near-duplicate markup twice.
- `web/src/components/SimilarVideoStrip.tsx` - a horizontally-scrolling strip of similar-video cards (thumbnail, title, cosine distance to 3 decimal places), each linking to that video's own detail page - clicking through a similar-video strip should feel the same as clicking any other video card.
- `web/src/pages/VideoDetailPage.tsx` - pulls `videoId` from the route, calls `useVideoDetail(videoId)` (Stage 4), and renders: thumbnail + title + channel link (to `/channels/:channelId`, Stage 8's page) + score badge + view/like/comment counts + description + tags; an "NLP features" section (9 fields via `FeatureList`, or "Not computed yet for this video" if `nlp_features` is `null`); a "Vision features" section (3 fields, same graceful-null pattern); a "Similar videos" section using the strip component.

## What it should look like

Verified with 6 new tests in `web/src/pages/VideoDetailPage.test.tsx`, all via MSW-served `VideoDetail` payloads: a fully-featured video renders its title, a channel link pointing at the right `/channels/:id` URL, the score badge, formatted view count, description, and joined tags; a video with `nlp_features`/`vision_features` both `null` shows "Not computed yet for this video" exactly twice (once per section) rather than a blank section or a crash; a video with both feature sets present renders the real formatted values (`Sentiment mean` / `0.50`, `Clickbait score` / `0.30`); a video with one similar video renders its title and `distance 0.040`; a 404 response renders "Failed to load this video."

## What to look out for

- **The same "placeholder replaced by a real async page breaks the routing test" pattern from Stage 6 repeated here exactly as predicted** - `routes.test.tsx`'s `/videos/:videoId` test previously asserted on the placeholder's static `abc123` text; once `VideoDetailPage` became a real data-fetching component, it needed an MSW handler for `/api/videos/abc123` (a full, valid `VideoDetail` payload - every field is required by the TypeScript interface, so the mock has to supply all of them, not just the ones the test cares about) and an `await screen.findByText(...)` instead of a synchronous assertion. Stage 8 will need the identical fix for `/channels/:channelId` when `ChannelViewPage` stops being a placeholder - flagged again here since it's now a confirmed, recurring pattern across every "replace a Stage 5 placeholder" stage.
- **`FeatureList` and `SimilarVideoStrip` don't have their own dedicated test files** - both are simple enough (pure rendering of props, no logic beyond a null/empty check) that they're exercised thoroughly through `VideoDetailPage.test.tsx`'s assertions instead of duplicating coverage with isolated component tests. This is a deliberate proportionality call, not an oversight - contrast with `ScoreBadge` (Stage 6), which got its own test file specifically because it has real branching logic (the color/label decision) worth testing in isolation.
- **The "not computed yet" section renders identically whether the video has literally never been processed by `compute-nlp`/`compute-vision` (Phase 4) or those commands simply haven't been run yet on this specific video** - there's no way for the frontend to distinguish "will never have this" from "just not run yet," which matches the backend's own `None`-means-"not computed" semantics from Phase 5 exactly (no separate "pending" state exists anywhere in the data model).
- The channel link's `href` is asserted directly in a test (`toHaveAttribute('href', '/channels/UC_x')`) rather than just checking the link text - catching a class of bug (right text, wrong destination) that a text-only assertion would miss.

## How to run tests properly

```powershell
cd web
npx tsc -b
npx vitest run        # 8 files, 38 tests
npm run lint
npm run build
```

No backend changes in this stage - `GET /videos/{id}` already existed from Phase 5.
