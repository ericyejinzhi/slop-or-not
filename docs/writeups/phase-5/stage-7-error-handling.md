# Phase 5, Stage 7 - Centralized error handling

## What is being implemented

Two exception handlers in a new `src/sloppy/api/errors.py`, registered on the app via a `register_error_handlers(app)` function called from `create_app()`:

- `value_error_handler(request, exc: ValueError) -> JSONResponse`: returns `404` with `{"detail": str(exc)}`. Every `ValueError` currently raised anywhere in this app (`resolve_channel`, the Stage 2 `ingest_video`) is a "not found" case, so this blanket mapping is safe today.
- `integrity_error_handler(request, exc: IntegrityError) -> JSONResponse`: returns `409` with a generic `{"detail": "Conflicting or invalid data", "error": str(exc.orig)}`.

FastAPI's own `RequestValidationError` (malformed query params/request bodies against the Pydantic schemas) already returns `422` automatically with a useful body - no custom handler was written for it, since it already does the right thing.

## What it should look like

Both handlers are registered and importable, but neither is actually reachable through the live API surface as currently built - this is documented plainly rather than glossed over:

- `GET /videos/{id}`'s 404 uses an **explicit `session.get(Video, video_id) is None` check** in the router (Stage 5), not this `ValueError` handler - no code path in the videos router raises a bare `ValueError`.
- The `ingest_video`/`ingest_channel` functions that *do* raise `ValueError` only run inside a `BackgroundTask` (Stage 6) - a background task's exception is logged, not surfaced to the HTTP response, by design (that's the whole point of "fire-and-forget"). So `value_error_handler` currently protects nothing live, but exists so that any *future* endpoint that calls one of these functions synchronously gets a clean 404 instead of a raw 500.
- `POST /labels`' 422 for an invalid `label` value comes entirely from Pydantic's `Literal["up","down","skip"]` validation, before the database is ever touched - the label-value `CHECK` constraint that would raise an `IntegrityError` is therefore unreachable through the API as designed. `POST /labels`' 404 for a missing video is also an explicit check (Stage 6), not this handler.

Given this, **Stage 7's own tests exercise the handler functions directly** (calling them with a synthetic exception and inspecting the response) rather than trying to drive them through a live endpoint that can't currently reach them - this is stated explicitly in the test file's docstring rather than left implicit.

## What to look out for

- **Both handlers are currently defense-in-depth, not load-bearing for any endpoint that exists today.** This is worth remembering if a future endpoint is added that calls `resolve_channel`/`ingest_video`/`record_label` (or anything else that can raise these) synchronously - at that point these handlers would actually activate, and it's worth re-verifying end to end rather than assuming registration alone is sufficient.
- **The `ValueError -> 404` mapping is intentionally broad.** If a future `ValueError` is ever raised for a reason that isn't "not found" (e.g. a genuine bad-input validation error that should be 400), it would silently become a 404 instead - flagged as a known simplification in the handler's own docstring, to revisit if that ever actually happens rather than guarding against a hypothetical now.
- `app.exception_handlers[ValueError]`/`app.exception_handlers[IntegrityError]` is how the test suite confirms registration - Starlette (which FastAPI is built on) exposes registered handlers on this dict, keyed by exception type.

## How to run tests properly

```powershell
uv run pytest tests/test_api_errors.py -v
uv run pytest    # full suite - confirms Stage 5/6's 404/422 assertions still pass unaffected by this stage
uv run ruff check .
```

All 3 tests in `test_api_errors.py` are pure/fast (no DB, no network) - they call the async handler functions directly via `asyncio.run(...)` and inspect the returned `JSONResponse`.
