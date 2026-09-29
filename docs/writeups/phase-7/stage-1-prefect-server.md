# Phase 7, Stage 1 - Prefect dependency + docker-compose server

## What is being implemented

The infrastructure this whole phase sits on: `prefect` (3.8.7) added as a project dependency, and a new `prefect-server` service in `docker-compose.yml` running the official `prefecthq/prefect:3-python3.12` image with `prefect server start --host 0.0.0.0`, publishing port `4200` (its API + web UI), with a named volume (`prefectdata`, mounted at `/root/.prefect`) so flow-run history survives a container restart.

This mirrors the project's existing pattern of docker-composing infrastructure (`postgres`, `minio`, and Phase 5's `api`) - Prefect's server is genuinely infra in the same sense: a long-running service other things talk to, not application code. Unlike the `api` service, this one uses a public, pre-built image rather than a project-specific `Dockerfile`, since the server itself never needs to import any of this project's code (`sloppy`, `torch`, etc.) - only the *worker* that actually executes flow runs (a later stage) needs that, and it runs on the host via `uv run prefect worker start`, not inside this container.

## What it should look like

```
$ docker compose up -d prefect-server
$ curl http://localhost:4200/api/health
true

$ export PREFECT_API_URL=http://localhost:4200/api
$ uv run prefect flow ls
No flows found.
```

All of this was actually run, not just described: the image was pulled, the container reached a healthy state (`docker compose ps` showing `health: starting` -> healthy), `/api/health` returned `true`, `/` (the UI) returned `200`, and `uv run prefect flow ls` connected successfully and reported no flows (correct - none have been defined yet).

## What to look out for

- **Every `uv run prefect ...` invocation needs `PREFECT_API_URL` set in that shell first**, or Prefect falls back to spinning up a throwaway "ephemeral" server for that single command - it will *work*, but any flow runs it records disappear immediately and never show up in the docker-compose server's UI, which is confusing if you forget this step and go looking for a flow run that "should be there." `uv run prefect config set PREFECT_API_URL=...` persists this across sessions in Prefect's own profile config, but an env var (if set) always overrides that - both were set to the same value in this stage's verification, so either one works from here on.
- **Prefect's server is entirely self-contained** - its own SQLite database for flow/deployment/flow-run metadata, unrelated to the app's Postgres. There's no shared schema, no migration to run, nothing else to wire up for the server itself to work.
- **This container never runs any of this project's code.** A later stage needs a worker process (`uv run prefect worker start`) running on the host - inside the existing dev environment where `sloppy` and its heavy dependencies are already installed - to actually execute flow runs. Forgetting to start a worker is the single most likely reason a scheduled/deployed flow run would appear stuck in a "Scheduled" or "Pending" state forever in the UI - flagged now, in `docs/writeups/TODO.md` item 17, ahead of actually needing it.

## How to run tests properly

```powershell
docker compose up -d prefect-server
curl http://localhost:4200/api/health   # expect: true

export PREFECT_API_URL=http://localhost:4200/api   # or `set` on plain cmd.exe
uv run prefect flow ls

uv run pytest    # full backend suite - 158 passed, unaffected by this stage
```

No automated test was written for this stage - there's no application code yet, just infrastructure wiring. The manual checks above are the real verification, matching Phase 5 Stage 9's precedent for docker-compose infra additions.
