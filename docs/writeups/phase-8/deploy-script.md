# The deploy script: `scripts/deploy-aws.sh`

## What is being implemented
One command to put the app on AWS, update it, and check on it, so pausing (tearing it down to stop the billing) and resuming costs minutes of attention instead of an hour of following the runbook. It automates `docs/deploy-runbook.md` Parts C-F in the order that worked on the first real deployment (2026-10-20). The code is `src/sloppy/deploy_aws.py`; `scripts/deploy-aws.sh` is a thin wrapper.

## The commands
| Command | What it does |
|---|---|
| `up --plan-only` | checks your setup, runs `terraform plan`, prints it, stops. Creates nothing |
| `up` | plan, ask you to type `deploy`, `terraform apply`, then everything below |
| `refresh` | everything below, against a deployment that already exists |
| `status` | server state, Session Manager, whether the site answers, the hourly cost |
| `stop-dev.sh --destroy-aws` | (existing) removes it all |

"Everything below", in order: export a database snapshot (no comments); copy the thumbnails to S3 (only the missing ones); publish the video-only model; package the **committed** code; write the server's `.env`; wait for the server to register with Session Manager; install Docker, buildx, the Postgres client and swap (first time only); fetch the staged files; load the snapshot into an empty database; build and start the containers; then check the public site like a visitor (read-only, videos, a thumbnail, ingest refused, one test prediction).

## Safety rules it follows
- **It never changes or destroys what exists.** If the plan contains any change or destroy, it stops and tells you to review it. Only plans that purely add resources go ahead.
- **It asks first.** `up` shows how many resources it will create, the hourly cost, and needs `deploy` typed (or `--yes`).
- **The database password is generated once** and kept in `infra/terraform/.db_password` (git-ignored), because Terraform needs the same value on every run against the same state. `TF_VAR_db_password` overrides it.
- **Staged secrets are always removed.** The server's `.env` (database password, YouTube key), your snapshot (it contains your labels) and the code archive pass through the private models bucket and are deleted at the end, including when a step fails.
- **`refresh` can empty the live database.** The import script refuses a non-empty database, so when the database already holds data the server step stops the app, drops and recreates it, and re-imports. The app is down for a few minutes while the image rebuilds.

## Costs
While the deployment exists it bills about $0.11 an hour (server about $0.085, database about $0.02, disk and address a little), roughly $2.70 a day. A full `up` takes about 25-30 minutes, most of it waiting (the database about 7 minutes, the build 3-5, the first prediction downloads the models), so a deploy-and-look cycle costs well under a dollar. Check your Billing page for the real figures; these are list-price estimates.

## What to look out for
- **Windows and `bash`.** A bare `bash` on Windows can be WSL's launcher in System32, which cannot see this project's paths. The script finds Git for Windows' bash through `git --exec-path`; a test fails if it ever picks System32. Found while writing the tests.
- **CRLF in the code archive.** `git archive` on Windows converts line endings when `core.autocrlf` is on, which broke a server script on the first real deployment. The script archives with `-c core.autocrlf=false` and checks the archive for CRLF before uploading.
- **The drop-and-recreate path on RDS has not been run for real.** The fresh-deployment path is the one verified on 2026-10-20. `refresh` on a live deployment drops the database first; it uses `DROP DATABASE ... WITH (FORCE)` as the database owner, which RDS should allow, but that exact step was never exercised. If it fails, the app is stopped and the error says so; `up` (after a destroy) is the fallback.
- **Terraform apply and the permission check.** If you ask Claude Code to run `up`, the agent's permission check may refuse the `terraform apply` inside it, as it did with a plain `terraform apply`. Run it yourself from Git Bash (or with the `!` prefix) and it is unaffected.
- **Only committed code ships.** The script warns when you have uncommitted changes.
- **Only a purely additive plan is accepted**, so a Terraform change that modifies existing resources (a new instance type, for example) needs a manual `terraform plan` and apply first.

## Testing
`tests/test_deploy_aws.py` (33 tests, no AWS needed) covers the parsing, the real `.env.aws.example` template being fully filled by what the script supplies (so the two cannot drift apart unnoticed), the CRLF check, the password handling, a `bash -n` syntax check of every script sent to the server, the safety rules above (plan-only applies nothing; a plan that changes or destroys is refused; no confirmation means nothing is created; staged files are deleted even when a step fails), and the waiting and checking logic with fakes. What the tests cannot cover is a live run against AWS; `up --plan-only` is the safe real check.
