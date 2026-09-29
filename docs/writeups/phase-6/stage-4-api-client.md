# Phase 6, Stage 4 - API client layer

## What is being implemented

The frontend's entire connection to the backend, per the confirmed decision to hand-write types rather than generate them from OpenAPI:

- `web/src/api/types.ts` - TypeScript interfaces mirroring every schema in `src/sloppy/api/schemas.py` field-for-field (`VideoListItem`, `VideoDetail`, `NlpFeatureBreakdown`, `VisionFeatureBreakdown`, `SimilarVideo`, `ChannelDetail`, `LabelPoolItem`, `LabelCreateRequest`, `IngestRequest`, etc.). Datetime fields are typed `string` (FastAPI serializes them as ISO 8601), not `Date`.
- `web/src/api/client.ts` - a thin `fetch` wrapper: `get<T>(path)`/`post<T>(path, body)`, a `buildQuery(params)` helper for query strings, and an `ApiError` class (carries the HTTP status and parsed error body) thrown on any non-2xx response.
- `web/src/api/{videos,channels,labels,ingest}.ts` - one small module per backend resource, each just a couple of typed functions calling `get`/`post` with the right path and params.
- `web/src/api/hooks.ts` - the TanStack Query layer: `useVideos`, `useVideoDetail`, `useChannel`, `useLabelPool`, `useCreateLabel`, `useCreateIngest`, each a thin wrapper over the fetch functions above via `useQuery`/`useMutation`.
- `web/src/queryClient.ts` - a `createQueryClient()` factory (not a shared singleton), so `main.tsx` creates one real instance and tests can create isolated ones with no shared cache between test cases.
- `web/src/main.tsx` now wraps `<App />` in `<QueryClientProvider>`.

Requests go through `/api/*` (relative), which Stage 3's Vite dev-server proxy rewrites to `http://localhost:8000/*` - the frontend code never hardcodes a backend host, and the backend never needed `CORSMiddleware` added.

## What it should look like

```ts
// A component would call:
const { data, isLoading } = useVideos({ channel_id: 'UC_x', sort: 'score', order: 'desc' })
// data: VideoListResponse | undefined, fully typed

const { mutate } = useCreateLabel()
mutate({ video_id: 'abc123', label: 'down', labeler: 'alice' })
```

Verified with 12 tests across 3 files, all using MSW (`msw/node`) to intercept the real `fetch` calls these functions/hooks make - not mocking `fetch` itself or stubbing the functions:
- `client.test.ts` (6 tests): `buildQuery`'s param-encoding/omit-undefined behavior, `get`/`post` parsing successful responses, `ApiError` thrown with the right status/body on a non-2xx response.
- `hooks.test.tsx` (6 tests): `useVideos` fetches and returns real MSW-served data, including that query params actually appear in the request URL; `useVideoDetail` stays `idle` when `videoId` is `undefined` (the `enabled` guard) and fetches correctly once one is provided; `useChannel` fetches channel details.

## What to look out for

- **A real TypeScript strict-mode gotcha, not a design choice**: `buildQuery`'s first version typed its parameter as `Record<string, string | number | undefined>`, which TypeScript refuses to accept a named interface argument for (e.g. `ListVideosParams`) unless that interface itself declares a string index signature - "Index signature for type 'string' is missing" - even via a generic type parameter (tried that too; same error, since generic constraint inference is stricter here than expected). Fixed by typing the parameter as plain `object` and casting internally when iterating with `Object.entries(...)`. Worth knowing if a similar "well-typed helper rejects a well-typed caller" error shows up again in later stages - the fix is almost always "loosen the parameter type and cast on the inside," not "make the caller's interface uglier by adding an index signature it doesn't need for anything else."
- **`useLabelPool` sets `staleTime: Infinity` and `refetchOnWindowFocus: false`** - a deliberate choice, not a TanStack Query default. The labeling page (a later stage) fetches a pool once and the user works through it card by card; TanStack Query's normal background-refetch behavior would silently reshuffle/refresh the pool out from under an in-progress labeling session, which is exactly wrong for this use case (mirrors the CLI's own "fetch the pool once per session" behavior from Phase 2).
- **`useCreateIngest` invalidates the `['videos']` query on success but has no way to know when the background ingest actually finishes** - per Phase 5's confirmed fire-and-forget design, there's no push notification. The invalidation just means "the next time something looks at the video list, fetch fresh" rather than "refresh now because new data landed."
- Every fetch/hook function was tested through MSW's real network-layer interception, not by mocking the functions themselves - this exercises the actual `fetch` call, URL construction, and JSON parsing, catching the kind of bug (like the query-param encoding) that a mocked-function test would hide.

## How to run tests properly

```powershell
cd web
npx tsc -b            # type-check
npx vitest run        # 3 files, 12 tests
npm run lint           # oxlint
npm run build          # production bundle
```

No backend changes in this stage.
