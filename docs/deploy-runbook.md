# Deployment runbook: a public, read-only dashboard on AWS (us-east-2)

The steps, in order, from an empty AWS account to a public URL. Commands marked **laptop** run in Git Bash on your machine; commands marked **server** run in a Session Manager shell on the EC2 instance.

**Status, stated plainly:** this was run end to end on real AWS on 2026-10-20 (apply, data steps, server setup, public checks) and the steps below are the corrected ones. What that run found is in the troubleshooting table at the bottom; the main ones were the Free Tier instance-type limit, the missing Docker `buildx` plugin, and presigned thumbnail links signed for the wrong host (fixed in code). Measured on the server (`c7i-flex.large`, 4 GB): a first prediction took 27 s, later ones 8-11 s; the api container used about 1.4 GB; restarting the api took about 20 s. Everything costs real money while it exists (about $2 a day for the server plus about $0.50 for the database); Part G tears it all down.

What you end up with: `http://<server ip>/` serving the dashboard (Videos and Channels), read-only, with scores precomputed locally. No ingestion or labeling in the cloud (a visitor can check a pasted video link, which changes nothing). The first deployment is deliberately the smallest useful one.

## The short way: one command (once Parts A and B are done)
Parts C to F are automated by `scripts/deploy-aws.sh` (details: `docs/writeups/phase-8/deploy-script.md`). Run it from the main checkout with the local stack up (`bash scripts/start-dev.sh`):
```
bash scripts/deploy-aws.sh up --plan-only   # shows what would be created; changes nothing
bash scripts/deploy-aws.sh up               # creates everything, loads your data, checks the site
bash scripts/deploy-aws.sh refresh          # after new labeling: push new data, model and code
bash scripts/deploy-aws.sh status           # is it up?
bash scripts/stop-dev.sh --destroy-aws      # tear it down; stops the billing
```
Only committed code is deployed, so commit first. The manual steps below are what the script does, kept as the reference and for when something needs fixing by hand.

## Part A - AWS account (console, once)
1. Create the account. Turn on **MFA for the root user**, then stop using root.
2. Billing -> **Budgets**: create a monthly cost budget (for example $20) that emails you at 50%, 80% and 100%. Do this before creating anything.
3. Create a deploy identity for the CLI: an **IAM Identity Center user** (or an IAM user with an access key). For a personal sandbox, admin rights are acceptable while you apply Terraform; narrow them later.

## Part B - Your machine (laptop)
```
aws --version ; terraform version         # open a NEW terminal after installing (PATH)
aws configure --profile deployer           # keys from Part A, region us-east-2, output json
export AWS_PROFILE=deployer
aws sts get-caller-identity                # the Arn must NOT end in ":root"
```
Keep the admin profile named (`deployer`) and out of the default profile, so tools started elsewhere cannot use it. Use `export AWS_PROFILE=deployer` only in the terminal where you run Terraform and the data steps. Never paste keys into a chat.

## Part C - Create the infrastructure (laptop)
```
cd infra/terraform
curl -s https://checkip.amazonaws.com       # your public IP
cat > terraform.tfvars <<'EOF'
aws_region             = "us-east-2"
thumbnails_bucket_name = "slop-or-not-thumbs-YOURNAME-4821"
models_bucket_name     = "slop-or-not-models-YOURNAME-4821"
ssh_ingress_cidr       = "YOUR.IP.HERE/32"
EOF
export TF_VAR_db_password="$(openssl rand -hex 16)" ; echo "$TF_VAR_db_password"   # SAVE IT
terraform init
terraform plan -out=tfplan        # expect: Plan: 15 to add, 0 to change, 0 to destroy
terraform apply tfplan            # billing starts; the database takes several minutes
terraform output                  # rds_endpoint, app_public_ip, app_instance_id, bucket names
```
Bucket names must be globally unique (lowercase letters, digits, hyphens). `terraform.tfvars` is gitignored; the password only lives in your shell and in the Terraform state file (`terraform.tfstate`, also gitignored: do not commit or share it). If you close the terminal, export `TF_VAR_db_password` again before any later `terraform` command.

**A passing plan does not prove the apply will work.** `terraform plan` never asks AWS whether a value is allowed, only `apply` does. The first real apply failed this way: the database was pinned to Postgres `16.4`, which RDS in `us-east-2` no longer offers (`InvalidParameterCombination: Cannot find version 16.4 for postgres`). The Terraform now asks for just major version `16` so RDS picks its current default. Terraform applies as much as it can, so a failure like that leaves the other resources created; fix the cause and run `terraform plan -out=tfplan` and `terraform apply tfplan` again, and only the missing piece is added. You can check what AWS offers yourself (read-only):
```
aws rds describe-db-engine-versions --engine postgres --default-only --engine-version 16 --query "DBEngineVersions[].EngineVersion" --output text --region us-east-2
aws rds describe-orderable-db-instance-options --engine postgres --engine-version 16.13 --db-instance-class db.t4g.micro --region us-east-2 --query "OrderableDBInstanceOptions[].DBInstanceClass" --output text
```

## Part D - Move the data (laptop)
```
# 1. a snapshot of the local database (no raw comments; only the scores of the active model
#    and of the video-only model, if VIDEO_ONLY_MODEL_* is set in your .env)
bash scripts/export-snapshot.sh snapshot.dump

# 2. the thumbnails: local MinIO -> your S3 bucket (1,031 files, ~131 MB; safe to re-run)
slop deploy copy-thumbnails --dest-bucket <thumbnails bucket> --dest-region us-east-2 --dry-run
slop deploy copy-thumbnails --dest-bucket <thumbnails bucket> --dest-region us-east-2

# 3. hand the snapshot to the server through S3 (the database is private, so only the
#    server can load it). The server's role may read the models bucket.
aws s3 cp snapshot.dump s3://<models bucket>/snapshots/snapshot.dump

# 4. publish the video-only model, so the server can fetch it for "Check a video".
#    `publish` sends to whatever S3 your environment points at, and your local .env points at
#    MinIO, so override those variables for this one command (blank = real S3 with your AWS
#    credentials). The version is VIDEO_ONLY_MODEL_VERSION in your local .env.
S3_ENDPOINT_URL= S3_ACCESS_KEY= S3_SECRET_KEY= S3_BUCKET_MODELS=<models bucket> AWS_REGION=us-east-2   slop model publish --model-name xgboost --model-version <video-only version>
```
The snapshot contains your labels; delete it from S3 once imported (Part E, step 5). `slop deploy copy-thumbnails` uses your `deployer` profile and never the local MinIO keys.

## Part E - Set up the server (server, via Session Manager)
Open it: AWS console -> EC2 -> Instances -> select the instance (`terraform output app_instance_id`) -> **Connect** -> **Session Manager**. (Needs a few minutes after the instance first starts. If Connect is greyed out or says the agent is not ready, wait and retry.)
```
sudo dnf install -y docker git postgresql16     # client must be version 16 or newer
sudo systemctl enable --now docker
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 \
     -o /usr/local/lib/docker/cli-plugins/docker-compose && sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
# docker compose needs the buildx plugin to build images; Amazon Linux's docker package does not include it
BUILDX=$(curl -sI https://github.com/docker/buildx/releases/latest | grep -i '^location' | sed 's#.*/tag/##' | tr -d '\r\n')
sudo curl -SL "https://github.com/docker/buildx/releases/download/$BUILDX/buildx-$BUILDX.linux-amd64" \
     -o /usr/local/lib/docker/cli-plugins/docker-buildx && sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-buildx
docker compose version && docker buildx version  # (use sudo for docker commands in this session)
```
The server is a `c7i-flex.large` (4 GB; an AWS Free Tier plan account is only allowed a short list of instance types and refuses `t3.medium`): the api process peaks around 1.7 GB resident once the three models behind "Check a video" are loaded, which a 2 GB `t3.small` cannot hold. On a normal paid account `t3.medium` is cheaper; set `app_instance_type` to use it. A build can still run short of memory (it installs torch). If a build dies with "Killed", add swap: `sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile`.
```
# 1. the code (a private repo needs a read-only personal access token as the password)
git clone https://github.com/<you>/slop-or-not.git && cd slop-or-not

# 2. the snapshot, then load it into RDS (the script refuses a non-empty database)
aws s3 cp s3://<models bucket>/snapshots/snapshot.dump .
export PGHOST=<rds host, no port> PGUSER=slop PGPASSWORD=<your db password> PGDATABASE=slopornot PGSSLMODE=require
bash scripts/import-snapshot.sh snapshot.dump <thumbnails bucket>

# 3. the app's configuration
cp .env.aws.example .env && nano .env            # fill in the <...> values; keep S3_* BLANK, not deleted

# 4. start it (the second file stops the base file from using local postgres/minio)
sudo docker compose -f docker-compose.yml -f docker-compose.aws.yml up -d --build api web

# 5. clean up the snapshot (it contains labels)
rm snapshot.dump
```
Then from your laptop: `aws s3 rm s3://<models bucket>/snapshots/snapshot.dump`.

## Part F - Verify
- Open `http://<app_public_ip>/`. The Videos page lists videos **with thumbnails and scores**; the Channels page ranks channels; there is no ingest form and no Label/Labeled link.
- `curl http://<app_public_ip>/api/config` returns `{"read_only":true}`.
- `curl -X POST http://<app_public_ip>/api/ingest -H 'content-type: application/json' -d '{"channel":"@x"}'` returns HTTP 403.
- `curl http://<app_public_ip>/api/config` also shows `"predict_enabled":true`, and the nav has a **Check a video** link. Paste a real video link there. **The first check downloads about 2 GB of models from Hugging Face and can take several minutes**; later ones take seconds to tens of seconds. Do one yourself so the first visitor does not.
- A prediction must change nothing: the Videos page count is the same before and after.
- On the server, `sudo docker compose ps` shows `api` healthy and `web` running; `sudo docker compose logs api | tail` shows no errors.

## Part G - Teardown (laptop)
```
cd infra/terraform
terraform destroy       # buckets are emptied automatically (force_destroy_buckets = true)
```
This deletes the database **without a final snapshot** (everything in it is a copy of your local data) and the server.

Shortcut for walking away: from the main checkout, `bash scripts/stop-dev.sh --destroy-aws` stops the local services, asks you to type `destroy`, runs the same `terraform destroy` (it does not need your DB password), and prints a before/after list of anything still billing. Plain `bash scripts/stop-dev.sh` only stops local services, but it also prints that read-only list so you can see what is still costing money. Check the console afterward for leftovers, and the Billing page the next day. The public IP changes if the instance is ever stopped and started (there is no Elastic IP).

## If something goes wrong
| Symptom | Likely cause |
|---|---|
| `terraform plan` asks for `var.db_password` | `TF_VAR_db_password` is not set in this terminal |
| Plan mentions `us-east-1` or `CHANGE-ME` | `terraform.tfvars` missing or in the wrong folder |
| Images load nowhere, broken thumbnails | `copy-thumbnails` not run, or the import was given a different bucket name than the one Terraform created |
| API errors mentioning `localhost:9000` or "Invalid endpoint" | `S3_ENDPOINT_URL` deleted instead of blank in the server `.env` |
| API can't reach the database | wrong `POSTGRES_HOST` (host only, no `:5432`), or `POSTGRES_SSLMODE` missing |
| `docker compose` starts postgres/minio containers | you forgot the `-f docker-compose.aws.yml` |
| Session Manager "agent not ready", or `aws ssm describe-instance-information` returns nothing, for more than ~10 minutes | The first deployment's server was built from the **Minimal** Amazon Linux 2023 image, which has no SSM agent, because the image was found by a loose name search. Fixed 2026-10-14 (the image now comes from AWS's own pointer for the standard edition). If your server predates the fix, replace it: `terraform apply -replace=aws_instance.app`. Check what a server runs with `aws ec2 describe-instances --instance-ids <id> --query "Reservations[0].Instances[0].ImageId"` then `aws ec2 describe-images --image-ids <ami>`; the name must NOT contain `minimal` |
| Session Manager "agent not ready" for the first few minutes | the instance is still starting; wait |
| `apply` fails with `InvalidParameterCombination: Cannot find version ... for postgres` | the pinned engine version was retired; use major version `16` (see Part C) and apply again |
| `apply` fails with `InvalidParameterCombination: The specified instance type is not eligible for Free Tier` | the account is on an AWS Free Tier plan, which only launches a short list of types. List them: `aws ec2 describe-instance-types --filters Name=free-tier-eligible,Values=true`. The default `c7i-flex.large` (4 GB) is on it; `t3.medium` is not |
| `docker compose build` says `compose build requires buildx 0.17.0 or later` | install the buildx plugin (Part E) |
| A script on the server fails with `set: pipefail: invalid option name` | it has Windows (CRLF) line endings, which happens when code is copied from Windows with an archive made while `core.autocrlf` is on. Clone it on the server, or make the archive with `-c core.autocrlf=false` |
| Thumbnails are broken and the image URL answers `AuthorizationQueryParametersError ... the region 'us-east-2' is wrong; expecting 'us-east-1'` | presigned links pointed at the global S3 host. Fixed in code (`storage.py`); rebuild the api image from a version that has the fix |
| The api log shows yt-dlp `Sign in to confirm you're not a bot` during a prediction | YouTube blocks yt-dlp from AWS addresses. Predictions still work: the thumbnail is taken from the YouTube API's URL instead. Nothing to do |
| `apply` failed partway | normal: what was created stays created. Fix the cause, then plan and apply again; Terraform only adds what is missing |
