# Phase 7, Stage 6 - Scheduled deployment

## What is being implemented

A new `slop orchestrate serve` command: `refresh_all_tracked_channels_flow.serve(name="daily-tracked-channels-refresh", cron="0 6 * * *")`. Calling `.serve()` on a Prefect flow does two things at once: it registers a real deployment (with the given name and cron schedule) against whichever Prefect API is configured, and it blocks, polling that API for scheduled/triggered runs of that deployment and executing them **in the calling process** - there's no separate "worker" concept needed, unlike Prefect's work-pool-based deployment model. This is the simplest mechanism Prefect offers for "run this on a schedule, unattended," and it matches the project's consistent bias toward the least infrastructure that genuinely satisfies the requirement (the same reasoning that chose FastAPI `BackgroundTasks` over a full job queue back in Phase 5).

This also means the guidance written into `docs/writeups/TODO.md` item 17 back in Stage 1 (which mentioned `prefect worker start --pool <pool-name>`) was based on the *other* Prefect deployment model and doesn't apply here - corrected in this stage to describe `slop orchestrate serve` instead, since that's the actual mechanism this project uses. Leaving Stage 1's original wording uncorrected would have pointed at a completely different (and here, unused) Prefect concept.

## What it should look like

```
$ export PREFECT_API_URL=http://localhost:4200/api
$ uv run slop orchestrate serve
```

(blocks, runs forever - meant to be left running, e.g. in its own terminal or as a background service)

```
$ curl -s -X POST http://localhost:4200/api/deployments/filter -d '{}' | ...
name: daily-tracked-channels-refresh
flow_id: c8247e25-cd05-4aaf-9ae5-df4d1bd8b5a0
schedules: [{'schedule': {'cron': '0 6 * * *', 'timezone': None, 'day_or': True}, 'active': True, ...}]
status: READY
```

This was actually run, not just described: `slop orchestrate serve` was started as a background process, and within seconds a real deployment named `daily-tracked-channels-refresh` appeared in the real docker-compose Prefect server, queried directly via its API - confirmed with an **active** cron schedule (`0 6 * * *`, i.e. 6am daily) and `status: READY`, meaning Prefect considers it correctly configured and ready to execute scheduled runs. This deployment is also visible at http://localhost:4200/deployments in the UI, satisfying the roadmap's "flow-run UI via local Prefect server" requirement directly.

## What to look out for

- **A schedule existing and being `active`/`READY` is not the same as a scheduled run having actually fired yet** - a `0 6 * * *` cron won't produce its first scheduled run until the next time the clock reads 6:00am in whatever timezone Prefect resolves (here, `timezone: None`, meaning UTC). Waiting for a real cron tick to arrive isn't practical to observe directly in an interactive session - the next stage verifies actual execution via a **manual trigger** of this same deployment instead, which exercises the identical execution path (the `serve()` process picking up a run and executing it) without needing to wait for the schedule itself to fire. This is the same category of deferral used throughout this project for anything that would require waiting on real-world time or real data - explicit, not hidden.
- **The `serve()` process must keep running for any scheduled (or manually-triggered) run to actually execute** - if it's killed, the deployment and its schedule still exist in the server (schedules aren't tied to any specific process), but every run created against it sits in a `Scheduled`/`Late` state forever until a `serve()` process for that flow starts polling again. `docs/writeups/TODO.md` item 17 now says this explicitly.
- **Corrected an already-published piece of guidance** (TODO.md item 17's `worker`/`work-pool` wording) rather than leaving it to quietly go stale - flagged here so it's clear this was a deliberate fix once the real mechanism was decided, not an inconsistency between stages.

## How to run tests properly

```powershell
export PREFECT_API_URL=http://localhost:4200/api
uv run slop orchestrate serve &     # or its own terminal; leave running

curl -s -X POST http://localhost:4200/api/deployments/filter -d '{}'
# confirm: name=daily-tracked-channels-refresh, schedule.cron="0 6 * * *", active=true, status=READY

# or open http://localhost:4200/deployments in a browser
```

No automated test covers `.serve()` itself (it's a blocking call by design, not something `pytest` can exercise without leaving a background process running past the test session) - this stage's verification is the manual run above, which was actually performed, not simulated.
