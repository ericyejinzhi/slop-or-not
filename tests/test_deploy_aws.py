"""The deploy script's logic, tested without AWS, Terraform or a server: parsing, the server
configuration, the safety rules (never change or destroy existing resources; always delete the
staged secrets) and a syntax check of every shell script it sends to the server."""

import io
import json
import subprocess
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from sloppy import deploy_aws as d
from sloppy.deploy_aws import DeployError, Local, Outputs

REPO = Path(__file__).resolve().parents[1]

OUTPUTS = Outputs(
    instance_id="i-123",
    public_ip="1.2.3.4",
    rds_host="db.example.us-east-2.rds.amazonaws.com",
    thumbs_bucket="thumbs-bucket",
    models_bucket="models-bucket",
)


def _local(tmp_path, **env) -> Local:
    values = {
        "ACTIVE_MODEL_VERSION": "v1",
        "VIDEO_ONLY_MODEL_NAME": "xgboost",
        "VIDEO_ONLY_MODEL_VERSION": "v2",
        "YOUTUBE_API_KEY": "yt-key-123456",
    }
    values.update(env)
    return Local(region="us-east-2", tfvars=tmp_path / "t.tfvars", env=values, password="pw-abc")


# --- parsing -----------------------------------------------------------------------------


def test_terraform_outputs_are_read_and_the_rds_port_is_dropped():
    raw = json.dumps(
        {
            "app_instance_id": {"value": "i-123"},
            "app_public_ip": {"value": "1.2.3.4"},
            "rds_endpoint": {"value": "db.example.us-east-2.rds.amazonaws.com:5432"},
            "thumbnails_bucket_name": {"value": "thumbs-bucket"},
            "models_bucket_name": {"value": "models-bucket"},
        }
    )

    outputs = d.parse_terraform_outputs(raw)

    assert outputs == OUTPUTS
    assert outputs.url == "http://1.2.3.4"


def test_missing_terraform_outputs_say_the_deployment_is_incomplete():
    with pytest.raises(DeployError, match="no output"):
        d.parse_terraform_outputs("{}")


def test_plan_summary_reads_the_counts_and_returns_none_when_nothing_changes():
    assert d.parse_plan_summary("Plan: 15 to add, 0 to change, 0 to destroy.") == (15, 0, 0)
    assert d.parse_plan_summary("Plan: 1 to add, 2 to change, 3 to destroy.") == (1, 2, 3)
    assert (
        d.parse_plan_summary("No changes. Your infrastructure matches the configuration.") is None
    )


def test_tfvars_values_are_read_with_a_default():
    # a tfvars file that does not exist yet falls back to the default
    assert d.read_tfvar(Path("/no/such/file.tfvars"), "aws_region", "us-east-2") == "us-east-2"


def test_tfvars_region_is_read_from_the_file(tmp_path):
    path = tmp_path / "x.tfvars"
    path.write_text('aws_region = "eu-west-1"\nother = "x"\n', encoding="utf-8")
    assert d.read_tfvar(path, "aws_region", "us-east-2") == "eu-west-1"


# --- the server's configuration ----------------------------------------------------------


def test_the_real_server_env_template_is_fully_filled_by_what_the_script_supplies(tmp_path):
    # Guards against the template and the script drifting apart: if someone adds a
    # <placeholder> to .env.aws.example without teaching the script, this fails here, not
    # in the middle of a deployment.
    template = (REPO / ".env.aws.example").read_text(encoding="utf-8")

    text = d.build_server_env(template, d.server_env_values(_local(tmp_path), OUTPUTS))

    assert "<" not in "".join(line for line in text.splitlines() if not line.startswith("#"))
    assert "POSTGRES_HOST=db.example.us-east-2.rds.amazonaws.com" in text
    assert "POSTGRES_PASSWORD=pw-abc" in text
    assert "S3_BUCKET_MODELS=models-bucket" in text
    assert "VIDEO_ONLY_MODEL_VERSION=v2" in text
    assert "YOUTUBE_API_KEY=yt-key-123456" in text
    # the three S3 variables must stay BLANK, not be deleted (see the runbook)
    for blank in ("S3_ENDPOINT_URL=", "S3_ACCESS_KEY=", "S3_SECRET_KEY="):
        assert any(line == blank for line in text.splitlines())
    assert "READ_ONLY=true" in text
    assert "TRUST_PROXY_HEADERS=true" in text


def test_a_value_with_no_matching_template_entry_is_an_error():
    with pytest.raises(DeployError, match="no entry for: NOT_THERE"):
        d.build_server_env("A=1\n", {"NOT_THERE": "x"})


def test_a_placeholder_left_unfilled_is_an_error():
    with pytest.raises(DeployError, match="unfilled placeholders in the server .env: HOST"):
        d.build_server_env("HOST=<fill me>\nA=1\n", {"A": "2"})


# --- the code archive --------------------------------------------------------------------


def _tar(tmp_path, name: str, content: bytes) -> Path:
    path = tmp_path / "code.tar.gz"
    with tarfile.open(path, "w:gz") as tar:
        info = tarfile.TarInfo(name)
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))
    return path


def test_a_script_with_windows_line_endings_is_caught(tmp_path):
    archive = _tar(tmp_path, "scripts/import-snapshot.sh", b"set -euo pipefail\r\necho hi\r\n")
    assert d.archive_has_windows_line_endings(archive) == ["scripts/import-snapshot.sh"]


def test_a_script_with_unix_line_endings_passes(tmp_path):
    archive = _tar(tmp_path, "scripts/import-snapshot.sh", b"set -euo pipefail\necho hi\n")
    assert d.archive_has_windows_line_endings(archive) == []


# --- the database password ---------------------------------------------------------------


def test_the_environment_password_wins_and_nothing_is_written(tmp_path):
    assert d.ensure_db_password(tmp_path, {"TF_VAR_db_password": "from-env"}) == "from-env"
    assert not (tmp_path / ".db_password").exists()


def test_a_new_password_is_generated_once_then_reused(tmp_path):
    first = d.ensure_db_password(tmp_path, {})
    second = d.ensure_db_password(tmp_path, {})

    assert first == second
    assert len(first) == 28 and first.isalnum()
    assert (tmp_path / ".db_password").read_text(encoding="utf-8") == first


def test_the_saved_password_file_is_git_ignored():
    ignore = (REPO / "infra" / "terraform" / ".gitignore").read_text(encoding="utf-8")
    assert ".db_password" in ignore.splitlines()


# --- what is sent to the server ----------------------------------------------------------


def _bash() -> str:
    try:
        return d.find_bash()
    except DeployError:
        pytest.skip("needs bash")


@pytest.mark.parametrize(
    "script",
    [
        d.INSTALL_SCRIPT,
        d.sync_script("models-bucket", "thumbs-bucket", "us-east-2"),
        d.BUILD_STATUS_SCRIPT,
        d.BUILD_LOG_SCRIPT,
    ],
    ids=["install", "sync", "build-status", "build-log"],
)
def test_every_server_script_is_valid_shell(script, tmp_path):
    path = tmp_path / "s.sh"
    path.write_text(script, encoding="utf-8", newline="\n")

    result = subprocess.run([_bash(), "-n", path.as_posix()], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr


def test_the_bash_it_picks_is_never_the_wsl_launcher():
    # On Windows a bare `bash` can be C:\Windows\System32\bash.exe (WSL), which cannot see
    # this project's paths.
    assert "system32" not in _bash().lower()


def test_the_sync_script_only_drops_a_database_that_holds_data():
    script = d.sync_script("m", "t", "us-east-2")

    drop = script.index("DROP DATABASE")
    guard = script.index('if [ "$HAS_TABLES" != "0" ]')
    end_of_guard = script.index("\nfi\n", guard)
    assert guard < drop < end_of_guard
    assert script.count("DROP DATABASE") == 1
    # the app is stopped before anything is dropped, and the snapshot is removed afterwards
    assert script.index("stop api web") < drop
    assert "rm -f snapshot.dump" in script


def test_the_sync_script_names_the_right_buckets_and_region():
    script = d.sync_script("my-models", "my-thumbs", "eu-west-1")
    assert "MODELS=my-models" in script
    assert "THUMBS=my-thumbs" in script
    assert "AWS_DEFAULT_REGION=eu-west-1" in script
    assert "BUILD_EXIT" in script


# --- the safety rules --------------------------------------------------------------------


def _patch_up(monkeypatch, tmp_path, plan_text, calls):
    monkeypatch.setattr(d, "load_local", lambda: _local(tmp_path))
    monkeypatch.setattr(d, "preflight", lambda local, need_docker=True: calls.append("preflight"))

    def fake_terraform(local, *args, streaming=False):
        calls.append(("terraform", args[0]))
        return plan_text if args[0] == "plan" else ""

    monkeypatch.setattr(d, "terraform", fake_terraform)
    monkeypatch.setattr(d, "get_outputs", lambda local: OUTPUTS)
    monkeypatch.setattr(d, "sync", lambda *a, **k: calls.append("sync"))
    monkeypatch.setattr(d, "summary", lambda outputs: calls.append("summary"))


def _args(**overrides):
    values = {"plan_only": False, "yes": True, "no_predict_check": False}
    values.update(overrides)
    return SimpleNamespace(**values)


def test_plan_only_never_applies_and_never_syncs(monkeypatch, tmp_path):
    calls = []
    _patch_up(monkeypatch, tmp_path, "Plan: 15 to add, 0 to change, 0 to destroy.", calls)

    d.cmd_up(_args(plan_only=True))

    assert ("terraform", "plan") in calls
    assert ("terraform", "apply") not in calls
    assert "sync" not in calls


def test_a_plan_that_would_destroy_or_change_anything_is_refused(monkeypatch, tmp_path):
    for plan in (
        "Plan: 1 to add, 0 to change, 1 to destroy.",
        "Plan: 0 to add, 1 to change, 0 to destroy.",
    ):
        calls = []
        _patch_up(monkeypatch, tmp_path, plan, calls)

        with pytest.raises(DeployError, match="changes or destroys"):
            d.cmd_up(_args())

        assert ("terraform", "apply") not in calls


def test_up_without_confirmation_creates_nothing(monkeypatch, tmp_path):
    calls = []
    _patch_up(monkeypatch, tmp_path, "Plan: 15 to add, 0 to change, 0 to destroy.", calls)
    monkeypatch.setattr("builtins.input", lambda prompt: "no")

    with pytest.raises(DeployError, match="not confirmed"):
        d.cmd_up(_args(yes=False))

    assert ("terraform", "apply") not in calls


def test_up_with_confirmation_applies_then_syncs(monkeypatch, tmp_path):
    calls = []
    _patch_up(monkeypatch, tmp_path, "Plan: 15 to add, 0 to change, 0 to destroy.", calls)
    monkeypatch.setattr("builtins.input", lambda prompt: "deploy")

    d.cmd_up(_args(yes=False))

    assert calls.index(("terraform", "apply")) < calls.index("sync") < calls.index("summary")


def test_up_on_infrastructure_that_already_exists_does_not_apply_again(monkeypatch, tmp_path):
    calls = []
    _patch_up(monkeypatch, tmp_path, "No changes. Your infrastructure matches.", calls)

    d.cmd_up(_args())

    assert ("terraform", "apply") not in calls
    assert "sync" in calls


def test_staged_secrets_are_deleted_even_when_a_step_fails(monkeypatch, tmp_path):
    cleared = []
    monkeypatch.setattr(d.boto3, "client", lambda *a, **k: object())
    monkeypatch.setattr(d, "clear_staging", lambda local, outputs: cleared.append(True))

    def boom(*args, **kwargs):
        raise DeployError("export failed")

    monkeypatch.setattr(d, "stage_data", boom)

    with pytest.raises(DeployError, match="export failed"):
        d.sync(_local(tmp_path), OUTPUTS, check_predict=False, first_time=True, total=8, n=5)

    assert cleared == [True]


def test_clear_staging_removes_every_staged_file_and_never_raises(monkeypatch, tmp_path):
    deleted = []

    class FakeS3:
        def delete_object(self, Bucket, Key):  # noqa: N803 - boto3's own argument names
            deleted.append((Bucket, Key))

    monkeypatch.setattr(d.boto3, "client", lambda *a, **k: FakeS3())

    d.clear_staging(_local(tmp_path), OUTPUTS)

    assert {key for _, key in deleted} == set(d.STAGED_KEYS)
    assert {bucket for bucket, _ in deleted} == {"models-bucket"}

    def broken(*a, **k):
        raise d.ClientError({"Error": {"Code": "AccessDenied", "Message": "no"}}, "DeleteObject")

    monkeypatch.setattr(d.boto3, "client", broken)
    d.clear_staging(_local(tmp_path), OUTPUTS)  # must not raise


def test_main_reports_a_failure_in_plain_words_and_exits_nonzero(monkeypatch, capsys):
    def fail(args):
        raise DeployError("something specific went wrong")

    monkeypatch.setattr(d, "cmd_status", fail)

    code = d.main(["status"])

    assert code == 1
    assert "Stopped: something specific went wrong" in capsys.readouterr().out


# --- waiting on the server and checking the site ----------------------------------------


class FakeSsm:
    class exceptions:  # noqa: N801 - mirrors boto3's client.exceptions
        class InvocationDoesNotExist(Exception):
            pass

    def __init__(self, statuses, stdout="", stderr=""):
        self.statuses = list(statuses)
        self.stdout = stdout
        self.stderr = stderr

    def send_command(self, **kwargs):
        return {"Command": {"CommandId": "c-1"}}

    def get_command_invocation(self, **kwargs):
        status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        return {
            "Status": status,
            "StandardOutputContent": self.stdout,
            "StandardErrorContent": self.stderr,
        }


def test_a_successful_server_command_returns_its_output(monkeypatch):
    monkeypatch.setattr(d.time, "sleep", lambda s: None)
    ssm = FakeSsm(["InProgress", "Success"], stdout="all good\n")

    assert d.ssm_run(ssm, "i-1", "echo hi", timeout=60) == "all good\n"


def test_a_failed_server_command_raises_with_the_useful_tail(monkeypatch):
    monkeypatch.setattr(d.time, "sleep", lambda s: None)
    ssm = FakeSsm(["Failed"], stdout="step one ok\n", stderr="boom: disk full\n")

    with pytest.raises(DeployError, match="boom: disk full"):
        d.ssm_run(ssm, "i-1", "echo hi", timeout=60)


def test_wait_for_build_returns_on_success_and_reports_a_failed_build(monkeypatch):
    monkeypatch.setattr(d.time, "sleep", lambda s: None)
    answers = iter(["still building: step 3", "BUILD_EXIT=0"])
    monkeypatch.setattr(d, "ssm_run", lambda ssm, iid, script, timeout=0: next(answers))
    d.wait_for_build(object(), OUTPUTS)  # returns

    log_calls = iter(["BUILD_EXIT=1", "ERROR: something broke\nline 2"])
    monkeypatch.setattr(d, "ssm_run", lambda ssm, iid, script, timeout=0: next(log_calls))
    with pytest.raises(DeployError, match="something broke"):
        d.wait_for_build(object(), OUTPUTS)


def _site(monkeypatch, config=None, videos=None, thumb=200, ingest=403, predict=200):
    config = {"read_only": True, "predict_enabled": True} if config is None else config
    videos = (
        {"total": 5, "items": [{"thumbnail_url": "https://s3/x.jpg"}]} if videos is None else videos
    )

    def fake_http(url, method="GET", body=None, timeout=20):
        if url.endswith("/api/config"):
            return 200, json.dumps(config).encode()
        if "/api/videos" in url:
            return 200, json.dumps(videos).encode()
        if url.endswith("/api/ingest"):
            return ingest, b"{}"
        if url.endswith("/api/predict"):
            return predict, json.dumps({"score": 0.5}).encode()
        return thumb, b""

    monkeypatch.setattr(d, "http", fake_http)
    monkeypatch.setattr(d.time, "sleep", lambda s: None)


def test_a_healthy_site_has_no_problems(monkeypatch):
    _site(monkeypatch)
    assert d.verify(OUTPUTS, check_predict=True) == []


def test_each_public_check_reports_its_own_problem(monkeypatch):
    _site(monkeypatch, config={"read_only": False, "predict_enabled": True})
    assert any("NOT read-only" in p for p in d.verify(OUTPUTS, check_predict=False))

    _site(monkeypatch, thumb=403)
    assert any("thumbnails do not load" in p for p in d.verify(OUTPUTS, check_predict=False))

    _site(monkeypatch, ingest=200)
    assert any("ingest was not refused" in p for p in d.verify(OUTPUTS, check_predict=False))

    _site(monkeypatch, videos={"total": 0, "items": []})
    assert any("videos list" in p for p in d.verify(OUTPUTS, check_predict=False))

    _site(monkeypatch, predict=500)
    assert any("test prediction failed" in p for p in d.verify(OUTPUTS, check_predict=True))

    _site(monkeypatch, config={"read_only": True, "predict_enabled": False})
    assert any("not enabled" in p for p in d.verify(OUTPUTS, check_predict=True))
