# Phase 5, Stage 1 - FastAPI dependencies + app skeleton

## What is being implemented

The bare minimum to have a real, runnable FastAPI app: `fastapi` and `uvicorn[standard]` added as project dependencies, `httpx` added as a dev dependency (used only by `TestClient` in tests, never shipped), and `src/sloppy/api/app.py` - a `create_app()` factory building a `FastAPI(title="slop-or-not", version="0.1.0")` instance with a single `GET /health` endpoint, plus a module-level `app = create_app()` for uvicorn to import. No routers, no database access, no error handling yet - this stage only proves the process starts and responds.

## What it should look like

```
$ uv run uvicorn sloppy.api.app:app --reload --port 8000
INFO:     Uvicorn running on http://127.0.0.1:8000

$ curl http://localhost:8000/health
{"status":"ok"}

$ curl http://localhost:8000/openapi.json
{"openapi":"3.1.0","info":{"title":"slop-or-not","version":"0.1.0"},"paths":{"/health":{"get":{...}}}}
```

Visiting `http://localhost:8000/docs` in a browser renders Swagger UI with `/health` listed as the only endpoint. Both the automated test and a real manual run (`uv run uvicorn`, then `curl` against `/health`, `/docs`, and `/openapi.json`) were used to verify this stage - no synthetic-fixture DB work was needed since there's no DB access yet.

## What to look out for

- `create_app()` is a factory function, not a bare module-level `FastAPI()` instance - this matches the plan's intent of letting a fresh app be constructed later if ever needed (e.g. for isolated test configurations), even though nothing takes advantage of that yet.
- `uv sync` picked up `httpx` as already present transitively (via `huggingface-hub`, per Phase 4's dependency tree) - it's now also declared directly in `dependency-groups.dev`, which is the correct fix regardless, since relying on an undeclared transitive dependency for `TestClient` would silently break if `huggingface-hub` ever dropped it.
- Running the test suite prints a `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead`. This comes from the installed `fastapi==0.141.1`/`starlette==1.7.0` versions expecting a not-yet-widely-adopted `httpx2` package - it's a library-level heads-up, not a bug in this project's code, and `httpx`-based `TestClient` usage still works correctly today. Worth revisiting if a future `fastapi` upgrade actually requires the switch.
- No `[project.scripts]` entry was added for running the API - `uv run uvicorn sloppy.api.app:app` is the standard FastAPI invocation, and wrapping it in a custom script would be an unnecessary deviation from that convention (unlike `slop`, which is a genuinely custom CLI).

## How to run tests properly

```powershell
uv run pytest tests/test_api_app.py -v
uv run pytest    # full suite - should show one more passing test than before
uv run ruff check src/sloppy/api tests/test_api_app.py

# Manual check
uv run uvicorn sloppy.api.app:app --reload --port 8000
# in another terminal:
curl http://localhost:8000/health
# or open http://localhost:8000/docs in a browser
```
