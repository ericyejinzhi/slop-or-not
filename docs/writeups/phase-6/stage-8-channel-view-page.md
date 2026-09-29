# Phase 6, Stage 8 - Channel view page

## What is being implemented

The third real page, replacing Stage 5's placeholder at `/channels/:channelId`: channel-level stats (from `GET /channels/{id}`, Phase 6 Stage 1) plus that channel's own video grid (`GET /videos?channel_id=...`, reusing everything Stage 6 built).

Before writing the page itself, Stage 6's video grid was refactored into 3 reusable pieces, since this page needs the exact same sort/filter/pagination UI:

- `web/src/hooks/useVideoListState.ts` - the sort/order/filter/pagination state management, extracted from `VideoGridPage`. Takes an optional `fixedParams` object merged into every request - `VideoGridPage` calls it with none, `ChannelViewPage` calls it with `{ channel_id: channelId }` so the channel filter is baked in and not user-editable (there's no channel filter dropdown on this page - the URL already scopes it).
- `web/src/components/VideoListControls.tsx` - the sort/order/predicted-label `<select>`s, extracted verbatim from `VideoGridPage`.
- `web/src/components/VideoGrid.tsx` - the card grid + loading/error/empty states + Previous/Next pagination, extracted verbatim from `VideoGridPage`.
- `web/src/pages/VideoGridPage.tsx` - rewritten to just compose the three pieces above (now under 30 lines, down from the original single-file implementation).
- `web/src/pages/ChannelViewPage.tsx` - a channel header (title, handle, description, subscriber/video/view counts via `formatCount`, and a "Last ingested {date}" / "Never fully ingested" line depending on whether `last_ingested_at` is `null`) followed by the same `VideoListControls` + `VideoGrid` combination, scoped to this channel.

## What it should look like

Verified with 4 new tests in `web/src/pages/ChannelViewPage.test.tsx`: channel stats and its video grid render together from two independent MSW-mocked endpoints; a channel with `last_ingested_at` set shows "Last ingested ..." instead of "Never fully ingested"; the video-list request genuinely includes `channel_id=UC_x` in its query string (confirming the scoping actually reaches the network call, not just the component's props); a failed channel fetch shows "Failed to load this channel." All of Stage 6's original `VideoGridPage.test.tsx` tests still pass unmodified against the refactored page, confirming the extraction didn't change behavior.

## What to look out for

- **A real test collision found while writing this stage's tests, not a bug in the app**: the first version of the "renders channel stats and its video grid" test asserted `screen.getByText('@testchannel')`, which failed with "Found multiple elements" - the channel header shows the channel's own handle, and the mocked video card also displays `@testchannel` as its `channel_handle` field, so the same string legitimately appears twice on the page. Fixed by asserting `getAllByText('@testchannel')` has length 2 instead of assuming a single match - a reminder that once a page combines multiple data sources referencing the same entity (a channel's handle shown both in a header and on every one of its videos' cards), `getByText` assertions need to account for that instead of assuming uniqueness.
- **This stage did a same-behavior refactor of Stage 6's page alongside building a new one** - `VideoGridPage.tsx`'s behavior is unchanged (same defaults, same param-building, same UI), only its internal structure changed. This was verified by re-running Stage 6's own test file against the refactored code without modifying any of its assertions - if the refactor had changed behavior, those tests would have caught it.
- **`useVideoListState`'s `fixedParams` are spread last** into the returned `params` object, so a fixed param (like `channel_id` on the channel page) always wins over anything a user-facing control could set - there's no actual conflict today (there's no `channel_id` control on `ChannelViewPage`), but this ordering is deliberate protection against a future control accidentally overriding the page's own scoping.
- No dedicated test file was written for `VideoListControls`/`VideoGrid` in isolation - both are already thoroughly exercised through `VideoGridPage.test.tsx` (Stage 6) and now `ChannelViewPage.test.tsx` as well, so isolated component tests would be pure duplication.

## How to run tests properly

```powershell
cd web
npx tsc -b
npx vitest run        # 9 files, 42 tests
npm run lint
npm run build
```

No backend changes in this stage - `GET /channels/{id}` (Phase 6 Stage 1) and `GET /videos` (Phase 5) already existed.
