"""One-command AWS deployment: build it, refresh it with new data, check on it.

    bash scripts/deploy-aws.sh up              create everything and put the app online
    bash scripts/deploy-aws.sh up --plan-only  show what would be created; change nothing
    bash scripts/deploy-aws.sh refresh         push new data/code/model to an existing deployment
    bash scripts/deploy-aws.sh status          is it up? what does it cost?
    bash scripts/stop-dev.sh --destroy-aws     tear it all down (stops the billing)

This automates docs/deploy-runbook.md Parts C-F, in the order that worked on the first real
deployment (2026-10-20). Run it from the main checkout, with the local stack running
(`bash scripts/start-dev.sh`), because the data comes from your local database and MinIO.

What it needs: Terraform and your AWS credentials (the same ones `terraform apply` uses),
infra/terraform/terraform.tfvars, and in your .env the active and video-only model versions
and YOUTUBE_API_KEY. The database password is generated for you the first time and kept in
infra/terraform/.db_password (git-ignored), because Terraform needs the same value on later runs.

Only committed code is deployed (it is shipped with `git archive`), so commit first.
Staging files (the server's .env with its secrets, the database snapshot with your labels, the
code archive) are put in the private models bucket for the server to fetch and are deleted
again at the end, even if a step fails.
"""

import argparse
import io
import json
import os
import re
import secrets
import string
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError

REPO = Path(__file__).resolve().parents[2]
TF_DIR = REPO / "infra" / "terraform"
SERVER_DIR = "/opt/slop"
COMPOSE = "docker compose -f docker-compose.yml -f docker-compose.aws.yml"
# A well-known public video, for the one test prediction at the end.
CHECK_VIDEO = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
# Rough hourly cost while it exists (list prices; check your Billing page): server about
# $0.085, database about $0.02, disk and address a little. Used only to print a reminder.
APPROX_COST_PER_HOUR = 0.11

# Keys in the models bucket used to hand things to the server. All are deleted afterwards.
STAGED_KEYS = ("deploy/code.tar.gz", "deploy/env", "snapshots/snapshot.dump")


class DeployError(Exception):
    """A step failed; the message says what to do next."""


def say(message: str = "") -> None:
    print(message, flush=True)


def step(number: int, total: int, title: str) -> None:
    say(f"\n[{number}/{total}] {title}")


# ---------------------------------------------------------------------------------------
# Pure helpers (tested without AWS)
# ---------------------------------------------------------------------------------------


@dataclass
class Outputs:
    instance_id: str
    public_ip: str
    rds_host: str
    thumbs_bucket: str
    models_bucket: str

    @property
    def url(self) -> str:
        return f"http://{self.public_ip}"


def parse_terraform_outputs(raw_json: str) -> Outputs:
    """From `terraform output -json`. rds_endpoint is host:port; only the host is wanted."""
    data = json.loads(raw_json)
    try:
        return Outputs(
            instance_id=data["app_instance_id"]["value"],
            public_ip=data["app_public_ip"]["value"],
            rds_host=str(data["rds_endpoint"]["value"]).rsplit(":", 1)[0],
            thumbs_bucket=data["thumbnails_bucket_name"]["value"],
            models_bucket=data["models_bucket_name"]["value"],
        )
    except KeyError as exc:
        raise DeployError(
            f"terraform has no output {exc}. Is the deployment fully created? Run "
            "`bash scripts/deploy-aws.sh up`."
        ) from exc


def parse_plan_summary(text: str) -> tuple[int, int, int] | None:
    """(add, change, destroy) from a line like 'Plan: 15 to add, 0 to change, 0 to destroy.'
    None when the plan says there is nothing to do."""
    match = re.search(r"Plan: (\d+) to add, (\d+) to change, (\d+) to destroy", text)
    if match:
        return int(match[1]), int(match[2]), int(match[3])
    return None


def build_server_env(template: str, values: dict[str, str]) -> str:
    """Fill the server .env template. Every key in `values` must exist in the template, and
    no <placeholder> may be left behind, so a half-filled file can never be deployed."""
    wanted = set(values)
    lines = []
    for line in template.splitlines():
        match = re.match(r"^([A-Z0-9_]+)=(.*)$", line)
        if match and match.group(1) in values:
            wanted.discard(match.group(1))
            line = f"{match.group(1)}={values[match.group(1)]}"
        lines.append(line)
    if wanted:
        raise DeployError(f"the server .env template has no entry for: {', '.join(sorted(wanted))}")
    text = "\n".join(lines) + "\n"
    leftover = re.findall(r"^([A-Z0-9_]+)=.*<.*>.*$", text, flags=re.MULTILINE)
    if leftover:
        raise DeployError(f"unfilled placeholders in the server .env: {', '.join(leftover)}")
    return text


def read_env_file(path: Path) -> dict[str, str]:
    values = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    return values


def read_tfvar(tfvars: Path, name: str, default: str) -> str:
    if tfvars.exists():
        match = re.search(rf'^\s*{name}\s*=\s*"([^"]*)"', tfvars.read_text(encoding="utf-8"), re.M)
        if match:
            return match.group(1)
    return default


def archive_has_windows_line_endings(archive: Path) -> list[str]:
    """Names of text files in the code archive that contain CRLF. A shell script with CRLF
    fails on the server ("set: pipefail: invalid option name"); this happens when the archive
    is made on Windows with core.autocrlf on."""
    bad = []
    suffixes = (".sh", ".yml", ".yaml", ".conf", ".py", ".toml", ".env.example", "Dockerfile")
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            if member.isfile() and member.name.endswith(suffixes):
                data = tar.extractfile(member)
                if data is not None and b"\r\n" in data.read():
                    bad.append(member.name)
    return bad


def new_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(28))


def ensure_db_password(tf_dir: Path, environ: dict[str, str]) -> str:
    """TF_VAR_db_password if set, else the saved one, else a new random one that is saved.
    The same value must be used every time Terraform runs against the same state."""
    if environ.get("TF_VAR_db_password"):
        return environ["TF_VAR_db_password"]
    saved = tf_dir / ".db_password"
    if saved.exists() and saved.read_text(encoding="utf-8").strip():
        return saved.read_text(encoding="utf-8").strip()
    password = new_password()
    saved.write_text(password, encoding="utf-8")
    return password


# ---------------------------------------------------------------------------------------
# What runs on the server (through SSM Run Command, as root)
# ---------------------------------------------------------------------------------------

INSTALL_SCRIPT = """set -euo pipefail
command -v docker >/dev/null || dnf install -y docker
dnf install -y postgresql16 tar gzip >/dev/null
systemctl enable --now docker
PLUGINS=/usr/local/lib/docker/cli-plugins
mkdir -p $PLUGINS
if [ ! -x $PLUGINS/docker-compose ]; then
  GH=https://github.com/docker
  curl -fSL $GH/compose/releases/latest/download/docker-compose-linux-x86_64 \\
    -o $PLUGINS/docker-compose && chmod +x $PLUGINS/docker-compose
fi
# docker compose needs the buildx plugin to build images; Amazon Linux's package lacks it.
if [ ! -x $PLUGINS/docker-buildx ]; then
  BUILDX=$(curl -sI https://github.com/docker/buildx/releases/latest | grep -i '^location' \\
    | sed 's#.*/tag/##' | tr -d '\\r\\n')
  GH=https://github.com/docker
  curl -fSL "$GH/buildx/releases/download/$BUILDX/buildx-$BUILDX.linux-amd64" \\
    -o $PLUGINS/docker-buildx && chmod +x $PLUGINS/docker-buildx
fi
# The api image installs torch; a little swap keeps the build from being killed.
if ! swapon --show | grep -q swapfile; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
fi
docker compose version
docker buildx version
psql --version
"""


def sync_script(models_bucket: str, thumbs_bucket: str, region: str) -> str:
    """Fetch the staged code, config and snapshot, load the snapshot into an EMPTY database,
    and start the image build in the background. Safe to run on a live deployment: the app
    is stopped first, and a database that already holds data is dropped and recreated (the
    import script refuses a non-empty one)."""
    return f"""set -euo pipefail
export AWS_DEFAULT_REGION={region}
MODELS={models_bucket}
THUMBS={thumbs_bucket}
if [ -d {SERVER_DIR} ]; then
  (cd {SERVER_DIR} && {COMPOSE} stop api web >/dev/null 2>&1) || true
fi
mkdir -p {SERVER_DIR}
cd {SERVER_DIR}
find . -mindepth 1 -maxdepth 1 ! -name build.log -exec rm -rf {{}} +
aws s3 cp s3://$MODELS/deploy/code.tar.gz /tmp/code.tar.gz --only-show-errors
tar xzf /tmp/code.tar.gz && rm -f /tmp/code.tar.gz
aws s3 cp s3://$MODELS/deploy/env .env --only-show-errors
chmod 600 .env
aws s3 cp s3://$MODELS/snapshots/snapshot.dump snapshot.dump --only-show-errors

export PGHOST="$(grep '^POSTGRES_HOST=' .env | cut -d= -f2-)"
export PGPASSWORD="$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2-)"
export PGUSER=slop PGSSLMODE=require
HAS_TABLES=$(PGDATABASE=slopornot psql -At -X -c \\
  "select count(*) from information_schema.tables where table_schema='public'")
if [ "$HAS_TABLES" != "0" ]; then
  echo "the database already holds data: dropping and recreating it"
  PGDATABASE=postgres psql -v ON_ERROR_STOP=1 -X -q \\
    -c "DROP DATABASE IF EXISTS slopornot WITH (FORCE)" -c "CREATE DATABASE slopornot"
fi
export PGDATABASE=slopornot
bash scripts/import-snapshot.sh snapshot.dump $THUMBS
rm -f snapshot.dump

setsid nohup bash -c '{COMPOSE} up -d --build api web > {SERVER_DIR}/build.log 2>&1; \\
  echo "BUILD_EXIT=$?" >> {SERVER_DIR}/build.log' > /dev/null 2>&1 &
sleep 2
echo "build started"
"""


BUILD_STATUS_SCRIPT = (
    f'grep -a "BUILD_EXIT" {SERVER_DIR}/build.log || '
    f'echo "still building: $(tail -n 1 {SERVER_DIR}/build.log | cut -c1-160)"\n'
)
BUILD_LOG_SCRIPT = f"tail -n 25 {SERVER_DIR}/build.log | cut -c1-200\n"


# ---------------------------------------------------------------------------------------
# Talking to AWS and to the local machine
# ---------------------------------------------------------------------------------------


def run(command: list[str], cwd: Path = REPO, env: dict[str, str] | None = None) -> str:
    """Run a local command, streaming nothing, returning stdout. Raises DeployError with the
    tail of the output if it fails."""
    full_env = {**os.environ, **(env or {})}
    result = subprocess.run(
        command, cwd=cwd, env=full_env, capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0:
        tail = (result.stdout + result.stderr).strip().splitlines()[-15:]
        raise DeployError(f"`{' '.join(command[:3])}...` failed:\n  " + "\n  ".join(tail))
    return result.stdout


def run_streaming(command: list[str], cwd: Path = REPO, env: dict[str, str] | None = None) -> None:
    """Like run, but shows the command's output as it happens (terraform apply)."""
    result = subprocess.run(command, cwd=cwd, env={**os.environ, **(env or {})})
    if result.returncode != 0:
        raise DeployError(f"`{' '.join(command[:3])}...` failed (exit code {result.returncode}).")


def find_bash() -> str:
    """The bash that runs this project's scripts. On Windows a bare `bash` can be WSL's launcher
    in System32, which cannot see these paths and fails confusingly, so use Git for Windows'
    bash, located through git itself."""
    if os.name != "nt":
        return "bash"
    try:
        exec_path = run(["git", "--exec-path"]).strip()
        candidate = Path(exec_path).parents[2] / "bin" / "bash.exe"
        if candidate.exists():
            return str(candidate)
    except (DeployError, FileNotFoundError, IndexError):
        pass
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if "system32" in directory.lower():
            continue
        candidate = Path(directory) / "bash.exe"
        if candidate.exists():
            return str(candidate)
    raise DeployError("Git Bash was not found. Install Git for Windows and run this from Git Bash.")


def ssm_run(ssm, instance_id: str, script: str, timeout: int = 900) -> str:
    """Run a shell script on the server and return its output. Raises DeployError with the
    output if it fails."""
    sent = ssm.send_command(
        InstanceIds=[instance_id],
        DocumentName="AWS-RunShellScript",
        Parameters={"commands": [script], "executionTimeout": [str(timeout)]},
        TimeoutSeconds=max(timeout, 30),
    )
    command_id = sent["Command"]["CommandId"]
    deadline = time.time() + timeout + 60
    while time.time() < deadline:
        time.sleep(4)
        try:
            inv = ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
        except ssm.exceptions.InvocationDoesNotExist:
            continue
        if inv["Status"] not in ("Pending", "InProgress", "Delayed"):
            out = inv.get("StandardOutputContent", "")
            if inv["Status"] != "Success":
                err = inv.get("StandardErrorContent", "").strip().splitlines()[-12:]
                tail = out.strip().splitlines()[-8:]
                raise DeployError(
                    f"the server step failed ({inv['Status']}):\n  " + "\n  ".join(tail + err)
                )
            return out
    raise DeployError("timed out waiting for the server; check it with `status`.")


def wait_for_ssm(ssm, instance_id: str, timeout: int = 900) -> None:
    say("  waiting for the server to register with Session Manager (usually 1-3 minutes)...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        info = ssm.describe_instance_information(
            Filters=[{"Key": "InstanceIds", "Values": [instance_id]}]
        )["InstanceInformationList"]
        if info and info[0]["PingStatus"] == "Online":
            return
        time.sleep(10)
    raise DeployError(
        "the server never became reachable through Session Manager. If it was built from the "
        "wrong image, see the runbook's troubleshooting table."
    )


def http(url: str, method: str = "GET", body: dict | None = None, timeout: int = 20):
    """(status, bytes) without raising on HTTP error statuses."""
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        request.add_header("content-type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, b""


# ---------------------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------------------


@dataclass
class Local:
    region: str
    tfvars: Path
    env: dict[str, str]
    password: str

    @property
    def tf_env(self) -> dict[str, str]:
        return {"TF_VAR_db_password": self.password}


def load_local() -> Local:
    tfvars = TF_DIR / "terraform.tfvars"
    if not tfvars.exists():
        raise DeployError(
            f"{tfvars} not found. Create it from terraform.tfvars.example "
            "(see the runbook, Part B)."
        )
    return Local(
        region=read_tfvar(tfvars, "aws_region", "us-east-2"),
        tfvars=tfvars,
        env=read_env_file(REPO / ".env"),
        password=ensure_db_password(TF_DIR, dict(os.environ)),
    )


def preflight(local: Local, need_docker: bool = True) -> None:
    """Check tools, AWS access and local settings before anything is created. A plan does
    not use the local Docker stack, so --plan-only passes need_docker=False."""
    problems = []
    for name in ("terraform", "git"):
        try:
            run([name, "version" if name == "terraform" else "--version"])
        except (DeployError, FileNotFoundError):
            problems.append(f"`{name}` is not available on PATH")
    try:
        identity = boto3.client("sts", region_name=local.region).get_caller_identity()
        say(
            f"  AWS account {identity['Account']} as {identity['Arn'].split('/')[-1]}, "
            f"region {local.region}"
        )
    except (BotoCoreError, ClientError) as exc:
        problems.append(
            f"AWS credentials do not work ({exc.__class__.__name__}); run `aws configure`"
        )

    for key in ("ACTIVE_MODEL_VERSION", "VIDEO_ONLY_MODEL_NAME", "VIDEO_ONLY_MODEL_VERSION"):
        if not local.env.get(key):
            problems.append(f"{key} is not set in your local .env")
    if not local.env.get("YOUTUBE_API_KEY"):
        problems.append("YOUTUBE_API_KEY is not set in your local .env (the server needs it)")
    name = local.env.get("VIDEO_ONLY_MODEL_NAME", "")
    version = local.env.get("VIDEO_ONLY_MODEL_VERSION", "")
    if (
        name
        and version
        and not (REPO / "models_artifacts" / name / version / "model.joblib").exists()
    ):
        problems.append(
            f"the video-only model files are missing: models_artifacts/{name}/{version}"
        )

    if need_docker:
        try:
            running = run(["docker", "compose", "ps", "--status", "running", "--services"])
            for service in ("postgres", "minio"):
                if service not in running.split():
                    problems.append(
                        f"the local {service} container is not running (bash scripts/start-dev.sh)"
                    )
        except (DeployError, FileNotFoundError):
            problems.append("docker is not running")

    dirty = run(["git", "status", "--porcelain", "--untracked-files=no"]).strip()
    if dirty:
        say("  NOTE: you have uncommitted changes. Only committed code is deployed.")
    if problems:
        raise DeployError("cannot start:\n  - " + "\n  - ".join(problems))


def terraform(local: Local, *args: str, streaming: bool = False) -> str:
    command = ["terraform", *args]
    if streaming:
        run_streaming(command, cwd=TF_DIR, env=local.tf_env)
        return ""
    return run(command, cwd=TF_DIR, env=local.tf_env)


def get_outputs(local: Local) -> Outputs:
    return parse_terraform_outputs(terraform(local, "output", "-json"))


def server_env_values(local: Local, outputs: Outputs) -> dict[str, str]:
    """Everything the server's .env needs that .env.aws.example leaves as a <placeholder>."""
    return {
        "POSTGRES_HOST": outputs.rds_host,
        "POSTGRES_PASSWORD": local.password,
        "S3_BUCKET_THUMBNAILS": outputs.thumbs_bucket,
        "S3_BUCKET_MODELS": outputs.models_bucket,
        "AWS_REGION": local.region,
        "ACTIVE_MODEL_VERSION": local.env["ACTIVE_MODEL_VERSION"],
        "VIDEO_ONLY_MODEL_NAME": local.env["VIDEO_ONLY_MODEL_NAME"],
        "VIDEO_ONLY_MODEL_VERSION": local.env["VIDEO_ONLY_MODEL_VERSION"],
        "YOUTUBE_API_KEY": local.env["YOUTUBE_API_KEY"],
    }


def stage_data(local: Local, outputs: Outputs, workdir: Path) -> None:
    """Put everything the server needs into the private bucket."""
    s3 = boto3.client("s3", region_name=local.region)
    bucket = outputs.models_bucket

    say("  exporting the database snapshot (no comments)...")
    snapshot = workdir / "snapshot.dump"
    run([find_bash(), "scripts/export-snapshot.sh", snapshot.as_posix()])
    s3.upload_file(str(snapshot), bucket, "snapshots/snapshot.dump")

    say("  copying thumbnails to S3 (only the missing ones)...")
    from sloppy.config import get_settings
    from sloppy.db.models import Thumbnail
    from sloppy.db.session import session_scope
    from sloppy.storage import get_s3_client
    from sloppy.storage_copy import copy_objects, get_destination_client

    with session_scope() as session:
        objects = [(b, k) for b, k in session.query(Thumbnail.s3_bucket, Thumbnail.s3_key)]
    result = copy_objects(
        get_s3_client(get_settings()),
        get_destination_client(None, local.region),
        outputs.thumbs_bucket,
        objects,
    )
    say(
        f"    copied {result.copied} ({result.bytes_copied / 1e6:.1f} MB), "
        f"{result.skipped} already there"
    )
    if result.failed:
        raise DeployError("some thumbnails failed to copy:\n  " + "\n  ".join(result.failed[:5]))

    say("  publishing the video-only model...")
    from sloppy.models.artifact_store import upload_model

    upload_model(
        s3,
        bucket,
        REPO / "models_artifacts",
        local.env["VIDEO_ONLY_MODEL_NAME"],
        local.env["VIDEO_ONLY_MODEL_VERSION"],
    )

    say("  packaging the committed code...")
    archive = workdir / "code.tar.gz"
    # core.autocrlf=false: on Windows git would otherwise write CRLF into the shell scripts.
    run(
        [
            "git",
            "-c",
            "core.autocrlf=false",
            "archive",
            "--format=tar.gz",
            "-o",
            archive.as_posix(),
            "HEAD",
        ]
    )
    bad = archive_has_windows_line_endings(archive)
    if bad:
        raise DeployError("the code archive has Windows line endings in: " + ", ".join(bad[:5]))
    s3.upload_file(str(archive), bucket, "deploy/code.tar.gz")

    say("  writing the server's configuration...")
    template = (REPO / ".env.aws.example").read_text(encoding="utf-8")
    server_env = build_server_env(template, server_env_values(local, outputs))
    s3.upload_fileobj(io.BytesIO(server_env.encode("utf-8")), bucket, "deploy/env")


def clear_staging(local: Local, outputs: Outputs) -> None:
    """Delete the staged files (they hold secrets and your labels). Never raises."""
    try:
        s3 = boto3.client("s3", region_name=local.region)
        for key in STAGED_KEYS:
            s3.delete_object(Bucket=outputs.models_bucket, Key=key)
    except (BotoCoreError, ClientError) as exc:
        say(f"  WARNING: could not delete the staged files from the models bucket ({exc}).")
        say(f"  Delete {', '.join(STAGED_KEYS)} from s3://{outputs.models_bucket}/ yourself.")


def wait_for_build(ssm, outputs: Outputs, timeout: int = 1500) -> None:
    say("  building the app on the server (about 3-5 minutes)...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(30)
        out = ssm_run(ssm, outputs.instance_id, BUILD_STATUS_SCRIPT, timeout=120)
        if "BUILD_EXIT=0" in out:
            return
        if "BUILD_EXIT=" in out:
            log = ssm_run(ssm, outputs.instance_id, BUILD_LOG_SCRIPT, timeout=120)
            raise DeployError(
                "the build failed on the server:\n  " + "\n  ".join(log.splitlines()[-12:])
            )
    raise DeployError("the build took too long; check the server's /opt/slop/build.log.")


def verify(outputs: Outputs, check_predict: bool) -> list[str]:
    """Public checks, in the order a visitor hits them. Returns a list of problems."""
    problems = []
    base = outputs.url
    say("  waiting for the site to answer...")
    for _ in range(40):
        status, _ = http(f"{base}/api/config")
        if status == 200:
            break
        time.sleep(5)
    else:
        return ["the site did not answer at " + base]

    status, body = http(f"{base}/api/config")
    config = json.loads(body or b"{}")
    say(f"  config: {config}")
    if config.get("read_only") is not True:
        problems.append("the site is NOT read-only")

    status, body = http(f"{base}/api/videos?limit=1")
    videos = json.loads(body or b"{}")
    total = videos.get("total", 0)
    say(f"  videos: {total}")
    if status != 200 or not total:
        problems.append("the videos list is empty or failed")
    elif videos["items"][0].get("thumbnail_url"):
        t_status, _ = http(videos["items"][0]["thumbnail_url"])
        say(f"  first thumbnail: HTTP {t_status}")
        if t_status != 200:
            problems.append(f"thumbnails do not load (HTTP {t_status})")

    status, _ = http(f"{base}/api/ingest", "POST", {"channel": "@x"})
    say(f"  ingest is blocked: HTTP {status} (want 403)")
    if status != 403:
        problems.append(f"ingest was not refused (HTTP {status})")

    if check_predict:
        if not config.get("predict_enabled"):
            problems.append("Check a video is not enabled on the server")
        else:
            say("  one test prediction (the first one downloads the models; up to a minute)...")
            started = time.time()
            status, body = http(f"{base}/api/predict", "POST", {"url": CHECK_VIDEO}, timeout=300)
            took = time.time() - started
            if status == 200:
                say(f"  prediction: HTTP 200 in {took:.0f}s, score {json.loads(body)['score']:.2f}")
            else:
                problems.append(f"the test prediction failed (HTTP {status})")
    return problems


def sync(
    local: Local, outputs: Outputs, check_predict: bool, first_time: bool, total: int, n: int
) -> None:
    """Stage the data, then load it on the server and bring the app up. Always cleans up."""
    import tempfile

    ssm = boto3.client("ssm", region_name=local.region)
    try:
        step(n, total, "Putting your data, model and code where the server can fetch them")
        with tempfile.TemporaryDirectory() as tmp:
            stage_data(local, outputs, Path(tmp))

        step(n + 1, total, "Preparing the server")
        wait_for_ssm(ssm, outputs.instance_id)
        if first_time:
            say("  installing Docker and tools (about a minute)...")
            ssm_run(ssm, outputs.instance_id, INSTALL_SCRIPT, timeout=900)
        else:
            say("  (tools are already installed)")

        step(n + 2, total, "Loading the data and building the app on the server")
        say(
            ssm_run(
                ssm,
                outputs.instance_id,
                sync_script(outputs.models_bucket, outputs.thumbs_bucket, local.region),
                timeout=900,
            )
            .strip()
            .splitlines()[-1]
        )
        wait_for_build(ssm, outputs)

        step(n + 3, total, "Checking the public site")
        problems = verify(outputs, check_predict)
    finally:
        clear_staging(local, outputs)
    if problems:
        raise DeployError("the site is up but not right:\n  - " + "\n  - ".join(problems))


def summary(outputs: Outputs) -> None:
    say("\nDone. The site is live:")
    say(f"  {outputs.url}/")
    say(
        f"\nIt bills about ${APPROX_COST_PER_HOUR:.2f} an hour "
        f"(about ${APPROX_COST_PER_HOUR * 24:.2f} a day) while it exists."
    )
    say("When you pause, remove it all with:  bash scripts/stop-dev.sh --destroy-aws")
    say("After new labeling, push the changes with:  bash scripts/deploy-aws.sh refresh")


def cmd_up(args: argparse.Namespace) -> None:
    local = load_local()
    step(1, 8, "Checking everything is in place")
    preflight(local, need_docker=not args.plan_only)

    step(2, 8, "Planning the infrastructure (nothing is created yet)")
    terraform(local, "init", "-input=false")
    plan_text = terraform(local, "plan", "-input=false", "-out=tfplan", "-no-color")
    counts = parse_plan_summary(plan_text)
    existing = counts is None
    if existing:
        say("  the infrastructure already exists and matches; nothing to create")
    else:
        say(f"  plan: {counts[0]} to add, {counts[1]} to change, {counts[2]} to destroy")
        if counts[2] > 0 or counts[1] > 0:
            raise DeployError(
                "the plan changes or destroys existing resources, which this script will not do "
                "for you. Review it with `cd infra/terraform && terraform plan`."
            )
    if args.plan_only:
        say("\n--plan-only: stopping here. Nothing was created.")
        return

    if not existing:
        if not args.yes:
            answer = input(
                f"\nCreate {counts[0]} AWS resources now? It bills about "
                f"${APPROX_COST_PER_HOUR:.2f} an hour "
                "until you destroy it. Type 'deploy' to continue: "
            )
            if answer.strip() != "deploy":
                raise DeployError("not confirmed; nothing was created.")
        step(3, 8, "Creating the infrastructure (the database takes about 7 minutes)")
        terraform(local, "apply", "-input=false", "tfplan", streaming=True)
    else:
        step(3, 8, "Infrastructure already exists")

    step(4, 8, "Reading the new server's details")
    outputs = get_outputs(local)
    say(f"  server {outputs.instance_id} at {outputs.public_ip}")

    sync(local, outputs, check_predict=not args.no_predict_check, first_time=True, total=8, n=5)
    summary(outputs)


def cmd_refresh(args: argparse.Namespace) -> None:
    local = load_local()
    step(1, 5, "Checking everything is in place")
    preflight(local)
    outputs = get_outputs(local)
    say(f"  deployment at {outputs.url}")
    sync(local, outputs, check_predict=not args.no_predict_check, first_time=False, total=5, n=2)
    summary(outputs)


def cmd_status(args: argparse.Namespace) -> None:
    local = load_local()
    try:
        outputs = get_outputs(local)
    except DeployError:
        say(
            "No deployment found (nothing in the Terraform state). Create one with: "
            "bash scripts/deploy-aws.sh up"
        )
        return
    ec2 = boto3.client("ec2", region_name=local.region)
    ssm = boto3.client("ssm", region_name=local.region)
    state = ec2.describe_instances(InstanceIds=[outputs.instance_id])["Reservations"][0][
        "Instances"
    ][0]
    info = ssm.describe_instance_information(
        Filters=[{"Key": "InstanceIds", "Values": [outputs.instance_id]}]
    )["InstanceInformationList"]
    say(f"server:  {outputs.instance_id} {state['InstanceType']} {state['State']['Name']}")
    say(f"session: {info[0]['PingStatus'] if info else 'not registered'}")
    status, body = http(f"{outputs.url}/api/config", timeout=10)
    say(
        f"site:    {outputs.url}/  ->  "
        + ("up " + body.decode() if status == 200 else "not answering")
    )
    say(f"cost:    about ${APPROX_COST_PER_HOUR:.2f} an hour while it exists")
    say("remove:  bash scripts/stop-dev.sh --destroy-aws")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="deploy-aws", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    up = sub.add_parser("up", help="create the infrastructure and put the app online")
    up.add_argument("--plan-only", action="store_true", help="show the plan and stop")
    up.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    up.add_argument("--no-predict-check", action="store_true", help="skip the test prediction")
    up.set_defaults(func=cmd_up)
    refresh = sub.add_parser(
        "refresh", help="push new data, model and code to a running deployment"
    )
    refresh.add_argument("--no-predict-check", action="store_true")
    refresh.set_defaults(func=cmd_refresh)
    sub.add_parser("status", help="is it up?").set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except DeployError as exc:
        say(f"\nStopped: {exc}")
        return 1
    except KeyboardInterrupt:
        say(
            "\nInterrupted. Anything already created stays; run `status`, or destroy it with "
            "`bash scripts/stop-dev.sh --destroy-aws`."
        )
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
