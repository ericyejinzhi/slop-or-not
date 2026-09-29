# Phase 6, Stage 9 - Ingest-trigger UI

## What is being implemented

A small form, `web/src/components/IngestForm.tsx`, mounted at the top of `VideoGridPage` - the landing page - so the roadmap's own Phase 6 verify bullet ("paste a channel, ingest, watch scores appear") has a literal, concrete UI element to do the "paste a channel" step with. A text input (channel handle or id) and a submit button calling `useCreateIngest()` (Stage 4's mutation hook wrapping `POST /ingest`).

Since Phase 5's `POST /ingest` is fire-and-forget with no job-status tracking (a confirmed, deliberate design decision from that phase), the form's "success" state is honest about what it actually knows: submitting shows "Ingestion started for {target}. This runs in the background - check back in a bit." - not a progress bar, not "done," because the frontend genuinely has no way to know when (or whether) the background task finishes. Typing again after a result is shown clears that message (`reset()` on the mutation), so a second submission doesn't leave a stale success/error message hanging around next to a new attempt.

## What it should look like

```
$ npm run dev
# on http://localhost:5173/, at the top of the video grid:
#   [Ingest a channel] [@somechannel______________] [Ingest]
# after clicking Ingest:
#   "Ingestion started for @somechannel. This runs in the background - check back in a bit."
```

Verified with 4 new tests in `web/src/components/IngestForm.test.tsx`, all via MSW: the submit button is disabled with an empty input; submitting a channel sends the exact expected JSON body (`{"channel": "@somechannel"}`) to `POST /api/ingest` and shows the success message with the real `target` echoed back from the (mocked) response; a failing request shows "Failed to start ingestion"; typing again after a result clears the previous message.

## What to look out for

- **The success message is deliberately vague about outcome, not incomplete** - it cannot say "ingestion complete" or show progress, because Phase 5's backend design genuinely provides no way to know that. This is a direct, visible consequence of the fire-and-forget decision made back in Phase 5 - worth remembering if a future phase (7, with real Prefect orchestration) ever wants to upgrade this to a real progress indicator, since that would require Phase 5's API to grow a job-status endpoint first, not just a frontend change.
- **No client-side validation of the channel string** beyond "non-empty" - a malformed handle or a nonexistent channel id will fail on the backend (`resolve_channel`'s `ValueError`, raised inside the background task where it's invisible to the HTTP response, per Phase 5's own design) with no visible error in the UI at all. This is an accepted gap consistent with the backend's own fire-and-forget tradeoff, not something this stage tries to paper over.
- **`useCreateIngest`'s existing `onSuccess` handler (Stage 4) invalidates the `['videos']` query**, so after a successful ingest submission the video grid's next fetch (e.g. on the user manually refreshing, or navigating away and back) will pick up any new data - but nothing pushes a refresh automatically, matching the "no push notification" reality documented back in Stage 4.
- The form was placed on `VideoGridPage` specifically (not its own page/route) since it's meant to be the very first thing a new visitor interacts with when there's no data yet - matching the roadmap's own framing of the demo path starting from an empty state.

## How to run tests properly

```powershell
cd web
npx tsc -b
npx vitest run        # 10 files, 46 tests
npm run lint
npm run build
```

No backend changes in this stage - `POST /ingest` already existed from Phase 5.
