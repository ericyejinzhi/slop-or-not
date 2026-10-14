# Deployment runbook: a public, read-only dashboard on AWS (us-east-2)

The steps, in order, from an empty AWS account to a public URL. Commands marked **laptop** run in Git Bash on your machine; commands marked **server** run in a Session Manager shell on the EC2 instance.

**Status, stated plainly:** nothing here has been run against real AWS. The Terraform validates (`init`, `validate`, `fmt`), and the data migration, the read-only containers and the model fetch were each rehearsed locally against scratch copies (`docs/writeups/phase-8/`). The **server-side commands in Part E are the least tested**: they assume Amazon Linux 2023 and have never run on a real instance, so expect to adjust a package name or a flag. Everything costs real money while it exists; Part G tears it all down.

What you end up with: `http://<server ip>/` serving the dashboard (Videos and Channels), read-only, with scores precomputed locally. No ingestion, labeling or model scoring in the cloud. The first deployment is deliberately the smallest useful one.

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

## Part D - Move the data (laptop)
```
# 1. a snapshot of the local database (no raw comments; only the active model's scores)
bash scripts/export-snapshot.sh snapshot.dump

# 2. the thumbnails: local MinIO -> your S3 bucket (1,031 files, ~131 MB; safe to re-run)
slop deploy copy-thumbnails --dest-bucket <thumbnails bucket> --dest-region us-east-2 --dry-run
slop deploy copy-thumbnails --dest-bucket <thumbnails bucket> --dest-region us-east-2

# 3. hand the snapshot to the server through S3 (the database is private, so only the
#    server can load it). The server's role may read the models bucket.
aws s3 cp snapshot.dump s3://<models bucket>/snapshots/snapshot.dump
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
docker compose version                           # (use sudo for docker commands in this session)
```
A 2 GB instance can run short of memory while building the api image (it installs torch). If a build dies with "Killed", add swap: `sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile`.
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
- On the server, `sudo docker compose ps` shows `api` healthy and `web` running; `sudo docker compose logs api | tail` shows no errors.

## Part G - Teardown (laptop)
```
cd infra/terraform
terraform destroy       # buckets are emptied automatically (force_destroy_buckets = true)
```
This deletes the database **without a final snapshot** (everything in it is a copy of your local data) and the server. Check the console afterward for leftovers, and the Billing page the next day. The public IP changes if the instance is ever stopped and started (there is no Elastic IP).

## If something goes wrong
| Symptom | Likely cause |
|---|---|
| `terraform plan` asks for `var.db_password` | `TF_VAR_db_password` is not set in this terminal |
| Plan mentions `us-east-1` or `CHANGE-ME` | `terraform.tfvars` missing or in the wrong folder |
| Images load nowhere, broken thumbnails | `copy-thumbnails` not run, or the import was given a different bucket name than the one Terraform created |
| API errors mentioning `localhost:9000` or "Invalid endpoint" | `S3_ENDPOINT_URL` deleted instead of blank in the server `.env` |
| API can't reach the database | wrong `POSTGRES_HOST` (host only, no `:5432`), or `POSTGRES_SSLMODE` missing |
| `docker compose` starts postgres/minio containers | you forgot the `-f docker-compose.aws.yml` |
| Session Manager "agent not ready" | the instance is still starting; wait a few minutes |
