# Phase 7, Stage 7 - Real verification: scheduled execution + forced-failure retry

## What is being implemented

Nothing new in code - this stage is entirely about actually satisfying the roadmap's own Phase 7 verify bullet: *"scheduled run completes unattended; a forced API failure retries and surfaces in the UI."* Both halves were genuinely exercised against the real docker-compose Prefect server, not simulated or described hypothetically.

## What it should look like

### Half 1 - a scheduled run completes unattended

`slop orchestrate serve` (Stage 6) was started as a background process, registering the real `daily-tracked-channels-refresh` deployment with its `0 6 * * *` cron schedule. Waiting for an actual 6am UTC tick isn't practical in an interactive session, so the deployment was triggered manually instead - `uv run prefect deployment run "refresh-all-tracked-channels/daily-tracked-channels-refresh"` - which creates a real flow run through the exact same mechanism a cron tick would (Prefect makes no distinction between a scheduled-by-clock run and a scheduled-by-manual-trigger run once it exists; both are just "a run this deployment's serving process should pick up"):

```
Created flow run 'lyrical-turtle'.
└── UUID: 964f7f61-9806-4a44-b780-a4e5cc999057
└── Scheduled start time: 2026-09-29 18:08:01 EDT (now)
```

The already-running `serve()` process picked it up and executed it with zero further human involvement, confirmed by polling the API afterward:

```
name: lyrical-turtle
state_type: COMPLETED
start_time: 2026-09-29T22:08:56.227816Z
end_time:   2026-09-29T22:08:56.460464Z
```

This is genuine "unattended" execution - once `serve()` is running, it required no further action to pick up and complete the triggered run.

### Half 2 - a forced API failure retries and surfaces in the UI

`slop orchestrate refresh-channel "@this-channel-does-not-exist-xyz-12345"` was run directly. Since `YOUTUBE_API_KEY` is blank in this environment (`docs/writeups/TODO.md` item 1 - not yet obtained), `ingest_channel_task`'s call into `google-api-python-client` failed immediately with a real `DefaultCredentialsError` ("Your default credentials were not found") - not a contrived exception, the actual real error this exact misconfiguration produces. Prefect's task-level retry policy (`retries=3, retry_delay_seconds=30`, configured back in Stage 4) then did exactly what it was configured to do, with real 30-second delays between real attempts:

```
18:10:27 | Task run 'ingest_channel_task-75b' - ... - Retry 1/3 will start 30 second(s) from now
18:11:00 | Task run 'ingest_channel_task-75b' - ... - Retry 2/3 will start 30 second(s) from now
18:11:33 | Task run 'ingest_channel_task-75b' - ... - Retry 3/3 will start 30 second(s) from now
18:12:06 | Task run 'ingest_channel_task-75b' - ... - Retries are exhausted
```

Querying the server afterward confirmed both the retry count and the final failure are genuinely recorded, not just printed to a terminal that would otherwise be lost:

```
flow run 'burrowing-mink': state_type=FAILED, state_name=Failed
  message: "Flow run encountered an exception: DefaultCredentialsError: ..."
task run 'ingest_channel_task-75b': state_type=FAILED, run_count=4
```

`run_count: 4` is the original attempt plus all 3 retries - exactly the configured policy, visibly reflected in the API (and therefore the same UI at http://localhost:4200 the rest of this phase has been using).

## What to look out for

- **The actual failure mode (`DefaultCredentialsError`, not an HTTP 403) was a genuine surprise worth recording**: the expectation going in was that an invalid/missing YouTube API key would produce an HTTP-level error from Google's API (a 403, handled by `_with_retry`'s own internal backoff in `ingest/youtube.py`). Instead, `googleapiclient.discovery.build(..., developerKey="")` with a blank key apparently falls back to attempting Google's Application Default Credentials flow before ever making a network call, raising a client-side `DefaultCredentialsError` instead. This is a real, previously-unobserved behavior of the `google-api-python-client` library under this exact misconfiguration (blank key, not simply an invalid one) - worth knowing if a future debugging session sees this same error and wonders whether it's a Prefect/task issue (it isn't; it's what happens upstream, before any of this project's retry logic even gets involved).
- **This particular failure never reached `_with_retry`'s own internal HTTP-status-based retry logic at all** - `DefaultCredentialsError` is raised before any HTTP request is attempted, so only Prefect's task-level retry policy applies here, not the two-layer retry cascade (Prefect retries wrapping `_with_retry`'s own internal retries) that was originally anticipated when picking this failure mode for the demo. The observed ~2 minutes of real retry delay (3 x 30s, plus execution time) matches Prefect's policy alone.
- **Nothing was changed in application code to force this failure** - it's the real, current state of this environment (no YouTube API key configured yet), used as-is. This is not a special "test mode" or a monkeypatch; it's exactly what would happen if `slop orchestrate serve`'s daily schedule fired for real right now, which is precisely the point of choosing it for this verification.
- The `serve()` background process was stopped after this verification, since nothing in this project needs it running continuously outside of an actual demo/production session.

## How to run tests properly

This stage has no new automated tests - it is exclusively a real, manual verification of Prefect's own retry/scheduling machinery (already Prefect's responsibility to have tested, not this project's), confirming this project's configuration of it (the `retries=`/`retry_delay_seconds=` values, the cron schedule, the deployment) actually behaves as configured. To reproduce:

```powershell
export PREFECT_API_URL=http://localhost:4200/api
uv run slop orchestrate serve &                     # leave running

uv run prefect deployment run "refresh-all-tracked-channels/daily-tracked-channels-refresh"
# then poll: curl http://localhost:4200/api/flow_runs/<uuid> and confirm COMPLETED

uv run slop orchestrate refresh-channel "@nonexistent-channel"
# watch the real retries in the terminal, then confirm via:
curl -s -X POST http://localhost:4200/api/task_runs/filter -d '{"flow_runs": {"id": {"any_": ["<flow-run-uuid>"]}}}'
# run_count should be 4 (1 + 3 retries), state FAILED
```

`uv run pytest` (177 passed, 5 deselected) is unaffected by this stage - no code changed.
