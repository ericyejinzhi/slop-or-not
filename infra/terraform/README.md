# Phase 8 reference infrastructure-as-code

Terraform describing the AWS resources `ROADMAP.md`'s Phase 8 calls for: an S3 bucket (replacing MinIO), an RDS Postgres instance (replacing the docker-compose `postgres` service), and a single EC2 instance running `api` + `web` via docker-compose (the roadmap's own "simplest" option, over ECS).

**This has never been `terraform apply`d and describes no resources that currently exist.** There is no AWS account, credentials, or billing set up anywhere in this project's development environment - confirmed directly before writing any of this. It exists as reference architecture: real, valid, `terraform validate`-passing Terraform, ready to actually provision from whenever real AWS access exists and the decision is made to do so.

## What was actually verified, and how

```powershell
cd infra/terraform
terraform init -backend=false   # downloads the AWS provider plugin - succeeded
terraform fmt -check -diff      # confirms canonical formatting - passed, no changes needed
terraform validate              # confirms syntax + internal consistency (resource
                                 # references resolve, types check out) - "Success! The
                                 # configuration is valid."
terraform plan -var="db_password=placeholder"
# fails with: "Error: No valid credential sources found" - exactly the expected failure
# point given no AWS credentials exist here. This confirms the configuration itself is
# sound (it got past parsing and validation) and correctly requires real credentials to
# go any further - the intended boundary for this phase's scope.
```

## How this maps to the application's config

| Terraform output | `.env` variable | Notes |
|---|---|---|
| `thumbnails_bucket_name` | `S3_BUCKET_THUMBNAILS` | Must be globally unique across all of AWS - the default in `variables.tf` is a placeholder that must be changed |
| `rds_endpoint` | `POSTGRES_HOST`/`POSTGRES_PORT` | `rds_endpoint` is `host:port`; split across the two variables |
| (the EC2 instance's IAM role) | leave `S3_ACCESS_KEY`/`S3_SECRET_KEY` **unset** | `src/sloppy/storage.py::get_s3_client` (Phase 8 Stage 1) falls back to boto3's default credential chain - which resolves the instance's IAM role automatically - only when these are unset, not blank |
| - | `POSTGRES_SSLMODE=require` | RDS should always be connected to over TLS |
| - | `S3_ENDPOINT_URL=` (unset/commented out) | Leaving this unset lets boto3 resolve the real regional S3 endpoint instead of a hardcoded MinIO-style one |
| - | `AWS_REGION` | Should match `var.aws_region` |

## What's deliberately not automated here

- **Enabling pgvector on the RDS instance** - `CREATE EXTENSION vector;` is a SQL statement run against the database after it exists, not a Terraform resource. This is a manual step, tracked in `docs/writeups/TODO.md`.
- **Deploying the application onto the EC2 instance** - `ec2.tf` deliberately leaves `user_data` unset rather than baking in an untested, unreviewed shell script. The real steps (install Docker, clone the repo, configure `.env`, `docker compose up -d --build api web`) are documented in `docs/writeups/phase-8`'s stage write-up instead, to be run and verified manually once this is actually applied.
- **A remote Terraform state backend** (e.g. an S3 bucket + DynamoDB lock table for team use) - unnecessary for a reference config that has never been applied by anyone; local state is the right default until that changes.
- **DNS/TLS** (a real domain, an ACM certificate, HTTPS) - the roadmap's own verify bullet is "public URL serves the dashboard end-to-end," achievable via the EC2 instance's plain public IP over HTTP for a first pass; a real domain+TLS setup is a reasonable follow-up, not blocking.

## Security choices worth noting

- The S3 bucket blocks all public access (`aws_s3_bucket_public_access_block`, all four settings `true`) and enables default server-side encryption - the app reaches it only via presigned URLs or the EC2 instance's IAM role, never via a public bucket policy.
- RDS is `publicly_accessible = false` and only reachable from the app instance's own security group - never exposed directly to the internet.
- The EC2 instance's IAM role is scoped to exactly the 3 S3 actions the app actually calls (`GetObject`/`PutObject`/`ListBucket`), on exactly the one thumbnails bucket - not a wildcard policy.
- `ssh_ingress_cidr` defaults to `203.0.113.1/32` (an RFC 5737 documentation-only address, never a real routable host) - a deliberately non-functional placeholder, not "open to the world," forcing whoever applies this to consciously set it to their own IP first.
