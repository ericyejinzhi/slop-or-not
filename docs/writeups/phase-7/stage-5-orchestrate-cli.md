# Phase 7, Stage 5 - `slop orchestrate` CLI commands

## What is being implemented

A new Typer sub-app, `orchestrate_app` (mounted as `slop orchestrate`, matching the project's one-sub-app-per-phase-concern convention), with two commands that call the Stage 4 flows directly:

- `slop orchestrate refresh-channel <id_or_handle>` - runs `refresh_channel_flow` for one channel, in-process, printing the resulting summary dict's fields.
- `slop orchestrate refresh-all [--seed-channels-csv PATH]` - runs `refresh_all_tracked_channels_flow`, printing one line per channel refreshed plus a final count; exits `1` with a clear message if no tracked channels were found (mirroring the exit-code convention every other "nothing to do" CLI command in this project already uses).

These run flows **in-process, with no Prefect deployment, worker, or schedule needed** - calling a `@flow`-decorated Python function directly still executes it for real and records a real flow run against whichever Prefect API the environment is configured to use (the docker-compose server, if `PREFECT_API_URL` is set; an ephemeral ad hoc server otherwise). This is the fast path for manually testing a flow's real behavior; a deployment (a later stage) is what makes it run on a schedule, unattended, without a human invoking the CLI.

## What it should look like

```
$ export PREFECT_API_URL=http://localhost:4200/api
$ uv run slop orchestrate refresh-all
18:01:59 | INFO | Flow run 'finicky-badger' - Beginning flow run 'finicky-badger' for flow 'refresh-all-tracked-channels'
18:01:59 | INFO | Flow run 'finicky-badger' - View at http://localhost:4200/runs/flow-run/20163203-...
18:01:59 | INFO | Flow run 'finicky-badger' - No tracked channels found in data\seed_channels.csv - nothing to refresh.
18:02:00 | INFO | Flow run 'finicky-badger' - Finished in state Completed()
No tracked channels found in data\seed_channels.csv.
```

This was actually run, twice (once without `PREFECT_API_URL` set - Prefect transparently used the persisted profile config from Stage 1's `prefect config set`, not an env var - and once with it set explicitly), and both flow runs were confirmed genuinely recorded in the real docker-compose Prefect server by querying its API directly afterward:

```
$ curl -s -X POST http://localhost:4200/api/flow_runs/filter -d '{}' | ...
tremendous-crayfish COMPLETED
finicky-badger COMPLETED
```

Both real, both `COMPLETED`, both traceable to the real flow named `refresh-all-tracked-channels`. The "no tracked channels" outcome itself is correct and expected - `data/seed_channels.csv` is still header-only, per every prior phase's running "no real data yet" theme (`docs/writeups/TODO.md` item 2).

## What to look out for

- **A `@flow`-decorated function's very first invocation in a process can take noticeably longer than a plain CLI command** - Prefect's engine does real setup work (API handshake, flow/deployment registration bookkeeping) the first time a flow executes, which showed up during this stage's manual testing as the command initially exceeding a 30-second timeout before completing successfully. This isn't a hang or a bug - it's a one-time-per-process cost, and subsequent flow runs in the same process are fast. Worth knowing if a future manual test of `slop orchestrate ...` seems to sit quietly for a while before printing anything.
- **`PREFECT_API_URL` set via `uv run prefect config set` (Stage 1) persists across shells** (it's written to a Prefect profile config file on disk, not just an environment variable) - which is why the first test run in this stage connected to the real docker-compose server correctly even without re-exporting the env var in that particular shell. An env var, if set, still takes precedence over the profile config - both point at the same place here, so it made no observable difference, but it's worth knowing they're two different mechanisms that happen to agree.
- **These CLI commands do not require a running worker** - a worker (a later stage) is only needed for *deployed, scheduled* flow runs to actually execute; calling the flow function directly (via this CLI, or from a Python REPL, or from a test) always executes it immediately in the calling process, worker or not.

## How to run tests properly

```powershell
uv run slop orchestrate --help
uv run slop orchestrate refresh-channel --help
uv run slop orchestrate refresh-all --help

uv run pytest    # full suite - unaffected by this stage (no new test file; the CLI
                  # commands are thin wrappers over the already-tested flow functions,
                  # verified here by actually running them, not by a new automated test)
uv run ruff check .
```

No new automated test file was added for this stage - `refresh_channel_command`/`refresh_all_command` are deliberately thin (parse args, call the flow, print the result), and the flow functions themselves already have thorough coverage in `tests/test_flows_refresh.py` (Stage 4). This stage's real verification is the manual CLI run shown above, actually executed against the real Prefect server.
