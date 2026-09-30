# Phase 8 - AWS migration + polish (full write-up)

This covers the whole of Phase 8 end-to-end. For stage-by-stage detail, see `stage-1-aws-config-compatibility.md` through `stage-4-readme-overhaul.md` in this same directory.

## What is being implemented

Per the scope confirmed with the user, this phase is **code/config preparation only - no real AWS account, credentials, or billable resources were touched anywhere**. There is no AWS CLI or credentials configured in this environment at all, confirmed directly before starting. Everything built here makes the codebase genuinely ready to run against real AWS services via env-var changes alone, plus real (never-applied) reference Terraform, without ever provisioning anything.

Built across four stages:

1. **AWS S3 + RDS config compatibility** - `s3_endpoint_url`/`s3_access_key`/`s3_secret_key` all made `None`-able (real AWS S3 needs none of them set the way MinIO does), a new `aws_region` setting, and `postgres_sslmode` support for RDS's TLS requirement. All backward-compatible - local dev behavior is completely unchanged.
2. **Production frontend serving** - `web/Dockerfile` + `web/nginx.conf`, a new `web` docker-compose service reverse-proxying `/api/*` to `api` exactly like the Vite dev server already does, so the frontend's application code never changes between dev and this container.
3. **Reference Terraform** (`infra/terraform/`) - S3, RDS, and a single EC2 instance with a least-privilege IAM instance role, genuinely validated locally (`terraform init`/`validate`/`fmt`) but never `apply`d.
4. **README overhaul** - an architecture diagram, a rubric summary, honest placeholders for ablation results and a demo GIF (both blocked on real data, same as every prior phase), and deployment docs for both the local and AWS paths.

## Architecture, end to end

```
Local dev (unchanged):                    Docker-compose production path (new, Stage 2):
  uv run uvicorn ... --reload                docker compose up -d --build api web
  npm run dev (Vite proxy)                     web (nginx) --/api/*--> api --> postgres/minio
        |                                            |
        v                                            v
  postgres/minio (docker-compose)          same containers, same images, same code

AWS reference path (Stage 1 config + Stage 3 Terraform, never applied):
  .env: S3_ENDPOINT_URL unset, AWS_REGION set, S3_ACCESS_KEY/SECRET unset
        POSTGRES_HOST=<rds-endpoint>, POSTGRES_SSLMODE=require
        |
        v
  get_s3_client() -> boto3 resolves real S3 endpoint, falls back to the EC2
                      instance's IAM role for credentials (no keys on disk)
  database_url -> real RDS endpoint + ?sslmode=require
        |
        v
  Same docker-compose.yml's api+web services, running on a real EC2 instance
  provisioned by infra/terraform/ (S3 bucket, RDS instance, EC2 + IAM role,
  security groups) - genuinely valid, genuinely never run
```

## What it should look like

```powershell
# Local production-shaped smoke test (Stage 2, actually run)
$ docker compose up -d --build api web
$ curl http://localhost:8080/api/health
{"status":"ok"}
$ curl -o /dev/null -w "%{http_code}\n" http://localhost:8080/videos/abc123
200   # React Router client-side route, served via nginx's SPA fallback

# Reference IaC validation (Stage 3, actually run)
$ cd infra/terraform && terraform init -backend=false && terraform validate
Success! The configuration is valid.
$ terraform plan -var="db_password=placeholder"
Error: No valid credential sources found   # expected - no AWS account exists here
```

## What to look out for

**Three real things were found and fixed, not assumed**:
1. `get_s3_client` always passed explicit (even blank) AWS credentials, which would silently override boto3's default credential chain - meaning a real EC2 IAM instance role would never actually get used even if `S3_ACCESS_KEY`/`SECRET` were left blank in `.env`. Fixed by only passing them when both are actually set; verified by inspecting a real `boto3` client's resolved credentials directly (`client._request_signer._credentials`), not assumed from documentation.
2. `docker-compose.yml`'s `prefect-server` comment still described the work-pool/worker Prefect model, which Phase 7 Stage 6 had already replaced with `.serve()` - a stale comment caught and corrected while working in the same file for Stage 2's `web` service.
3. Terraform's failure mode was verified precisely: `terraform plan` fails with "No valid credential sources found," not a configuration error - confirming the Terraform itself is sound and the only missing piece is a real account, exactly the intended scope boundary.

**Design decisions worth remembering**:
- Every new `Settings` field defaults to the exact value that preserves current local-dev behavior - `s3_endpoint_url` still defaults to the MinIO URL, `postgres_sslmode` still defaults to `None` (no TLS param appended). Nothing about local development changed in this entire phase.
- The nginx `/api/` proxy target (`http://api:8000/`) is hardcoded to the docker-compose service name - correct for the EC2-with-docker-compose path this phase actually prepared for, but would need reconsidering for a different topology (e.g. the frontend deployed separately to S3+CloudFront, the roadmap's own "optionally" alternative) - not solved here, since only the "simplest" path was in scope.
- Every Terraform security default is deliberately non-functional rather than merely "reasonable" - a documentation-only IP for SSH ingress, an obviously-placeholder bucket name, no default database password at all - so a future `terraform apply` can't accidentally do something insecure by inheriting an untouched default.
- Enabling `pgvector` on RDS and deploying the app onto the EC2 instance are both explicitly manual, undocumented-as-automation steps (no Terraform `user_data`, no SQL migration for the extension) - tracked concretely in `docs/writeups/TODO.md` item 18 rather than silently deferred.

**No real AWS account exists, and this phase doesn't change that** - consistent with the "no real data yet" theme running through every phase, this one's version is "no real cloud infrastructure yet." Everything that *can* be verified without one (config defaults, boto3 client construction, Terraform syntax/validation, the local docker-compose production path) was verified for real; everything that needs a real account (an actual S3 bucket, an actual RDS connection, an actual public URL) is deferred and tracked.

## How to run tests properly

```powershell
# Backend
uv run pytest                    # 184 passed, 5 deselected
uv run ruff check .
uv run ruff format --check .

# Frontend
cd web
npx vitest run                   # 52 passed
npm run lint

# Docker-compose (local production path)
docker compose config --quiet
docker compose up -d --build api web
curl http://localhost:8080/api/health

# Terraform (reference only - never apply)
cd infra/terraform
terraform init -backend=false
terraform fmt -check -diff
terraform validate
```

## What's next

Phase 8's code is complete; per `ROADMAP.md`, this was the last planned phase. What remains is entirely manual and optional: getting real YouTube data through the pipeline (`docs/writeups/TODO.md` items 1-8, unchanged since Phase 2), and - whenever there's appetite for it - actually provisioning the AWS resources this phase prepared for (`docs/writeups/TODO.md` item 18) to get a real public URL, record a real demo GIF, and fill in the README's still-placeholder ablation/results section with real numbers.
