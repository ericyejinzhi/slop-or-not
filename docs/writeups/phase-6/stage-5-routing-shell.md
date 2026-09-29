# Phase 6, Stage 5 - Routing shell + layout/nav

## What is being implemented

The navigational skeleton all 4 real pages (Stages 6-10) will slot into:

- `web/src/routes.tsx` - `AppRoutes()`, a component containing just the `<Routes>` tree (no router itself), deliberately extracted from `App.tsx` so tests can wrap it in a `MemoryRouter` instead of `BrowserRouter` without duplicating the route definitions. Routes: `/` (video grid), `/videos/:videoId` (video detail), `/channels/:channelId` (channel view), `/label` (labeling), `*` (not-found).
- `web/src/App.tsx` - now just `<BrowserRouter><AppRoutes /></BrowserRouter>`.
- `web/src/components/Layout.tsx` - a shared header/nav (brand link + "Videos"/"Label" nav links, using React Router's `NavLink` for active-state styling) wrapping an `<Outlet />` for the current page.
- `web/src/pages/{VideoGridPage,VideoDetailPage,ChannelViewPage,LabelingPage,NotFoundPage}.tsx` - placeholder components for now, each stating plainly which later stage replaces it with real content (e.g. "Video grid coming in Stage 6"). `VideoDetailPage`/`ChannelViewPage` already pull `videoId`/`channelId` out of the URL via `useParams` and render them, proving route params flow through correctly even before the real page content exists.

## What it should look like

```
$ npm run dev
# http://localhost:5173/         -> "Videos" nav highlighted, "Video grid coming in Stage 6."
# http://localhost:5173/label    -> "Label" nav highlighted, "Labeling page coming in Stage 10."
# http://localhost:5173/videos/abc123  -> "Video detail for abc123 coming in Stage 7."
# http://localhost:5173/nonsense -> "Page not found." + a link back to /
```

Verified with 6 new tests in `src/routes.test.tsx`, using `MemoryRouter` (not `BrowserRouter`) so each test can start at an arbitrary path without touching the real browser URL: renders the right placeholder at each of the 4 real routes, renders the not-found page for an unmatched path, and a real `userEvent` click-through test (clicking "Label" then "Videos" in the nav and confirming the displayed page changes both times) - proving actual navigation works, not just that each route renders in isolation.

## What to look out for

- **The `App.tsx`/`routes.tsx` split exists specifically for testability** - `BrowserRouter` binds to the real browser history API, which doesn't play well with rendering multiple independent test cases at different starting URLs. `MemoryRouter` (React Router's in-memory router, built for exactly this) needs the routes tree without an outer `BrowserRouter` already wrapping it - hence extracting `AppRoutes` as its own component. Any future top-level routing change should go in `routes.tsx`, not `App.tsx`.
- **Every route-testing test also wraps `AppRoutes` in the same `createWrapper()` (QueryClientProvider) helper from Stage 4**, even though none of the current placeholder pages call a query hook yet - this is forward-looking: Stages 6-10 will replace these placeholders with real pages that do call `useVideos`/`useVideoDetail`/etc., and retrofitting the QueryClientProvider wrapper into every existing routing test later would be more error-prone than just including it now.
- `NotFoundPage` is a small, deliberate addition beyond the roadmap's literal 4-page list - a catch-all `path="*"` route is normal React Router practice and costs almost nothing, so it was included now rather than treated as a gap to notice later.

## How to run tests properly

```powershell
cd web
npx tsc -b
npx vitest run        # 4 files, 18 tests
npm run lint
npm run build
npm run dev            # manual click-through at http://localhost:5173
```

No backend changes in this stage.
