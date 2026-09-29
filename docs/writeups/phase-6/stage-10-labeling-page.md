# Phase 6, Stage 10 - Labeling page

## What is being implemented

The fourth and final real page, replacing Stage 5's placeholder at `/label` - a web equivalent of the CLI's `slop label run` (Phase 2), backed by `GET /labels/pool` (Phase 6 Stage 2) and `POST /labels` (Phase 5).

`web/src/pages/LabelingPage.tsx` fetches the labeling pool once via `useLabelPool({})` (Stage 4's hook, which deliberately has `staleTime: Infinity` so it doesn't silently refetch/reshuffle mid-session), then walks through it client-side with a local `index` (which item is currently shown) - the exact same "fetch once, iterate locally" shape as the CLI's own `run_labeling` loop. For the current item it shows the thumbnail, title, channel handle, published date, and view/like/comment counts (mirroring what the CLI prints for each video), plus three buttons - "(y) Up", "(n) Down", "(s) Skip" - and matching keyboard shortcuts (`y`/`n`/`s`), directly mirroring the CLI's own `y=up (quality) n=down (slop) s=skip` legend. Clicking a button or pressing its key calls `useCreateLabel()` (Stage 4), and on success advances `index` and increments a "Labeled N this session" counter.

A small "Labeler" text input at the top persists its value to `localStorage` (`slop-or-not:labeler`) so a repeat visitor doesn't have to retype their name every session - if left blank, the value sent is `undefined`, and the backend's own fallback to `Settings.labeler_name` (Phase 5) takes over, exactly like the CLI's `--labeler`/`LABELER_NAME` precedence.

## What it should look like

```
$ npm run dev
# at http://localhost:5173/label:
#   Labeler [___________]              Labeled 0 this session
#   [thumbnail]
#   Pool Video Title
#   @channelhandle · Jan 1, 2026
#   100 views · 10 likes · 2 comments
#   [(y) Up] [(n) Down] [(s) Skip]
```

Pressing `n` (or clicking "(n) Down") submits `{video_id, label: "down", labeler}`, advances to the next pool item, and increments the session counter - all confirmed by 6 new tests in `web/src/pages/LabelingPage.test.tsx`, all via MSW: an empty pool shows "No videos available to label"; a one-item pool renders its title, and clicking "(y) Up" submits the exact expected request body and advances past the end of the pool; pressing the `n` key (not clicking) submits a "down" label; labeling the only item in a pool ends on "Pool complete for this session" with "Labeled 1 this session" shown; typing into the Labeler field writes to `localStorage`; a failed pool fetch shows "Failed to load the labeling pool."

## What to look out for

- **The keyboard listener is deliberately re-registered on every render, with no dependency array on its `useEffect`** - this means React adds and removes a `window` keydown listener on literally every render, which is not the most performant pattern, but it was chosen specifically to avoid a stale-closure bug: `handleLabel` closes over `current`/`labeler`/`createLabel.isPending`, all of which change as the user labels through the pool, and a memoized/dependency-gated version would risk keeping a stale `current` (labeling the *previous* video) if the dependency array were ever written incorrectly. Given the pool size is small (tens, not thousands, of items per session) and re-running a `useEffect` is cheap, this trades a small amount of performance for eliminating an entire class of subtle bug - flagged explicitly here as a deliberate choice, not an oversight, since "effect with no deps" usually is a smell worth a second look.
- **The `/label` and nav-navigation tests in `routes.test.tsx` needed the same "placeholder replaced by a real async page" fix as Stages 6-8** - by this point a fully expected, no-longer-surprising pattern across every stage that swaps a Stage 5 placeholder for a real page.
- **The pool never re-fetches mid-session even if you label every item** - "Pool complete for this session" is a terminal state for that fetch; getting a fresh pool (e.g. to keep labeling) requires a full page reload, which re-runs `useLabelPool` and gets a newly shuffled, freshly unlabeled-only set. This matches the CLI's own behavior exactly (a `slop label run` session ends when its pool is exhausted; running the command again starts a new one) - not a bug, a faithful port of the existing design.
- **No consistency-mode UI was built** - `GET /labels/pool?mode=consistency` (Phase 2's relabeling spot-check) exists on the backend but has no corresponding control on this page (e.g. a mode toggle). This is a real, acknowledged gap, not something this stage's tests hide - the web labeling page currently only supports the CLI's default "pool" mode. Worth a follow-up if the consistency workflow needs a web equivalent later.
- `localStorage` access is wrapped in `try`/`catch` (both read and write) even though this is a normal browser app, not a sandboxed context with unusual storage restrictions - a cheap defensive habit that costs nothing and means a private-browsing edge case degrades to "the labeler field doesn't persist" instead of crashing the page.

## How to run tests properly

```powershell
cd web
npx tsc -b
npx vitest run        # 11 files, 52 tests
npm run lint
npm run build
```

No backend changes in this stage - `GET /labels/pool` (Phase 6 Stage 2) and `POST /labels` (Phase 5) already existed.
