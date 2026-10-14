import boto3

from sloppy.config import Settings


def test_database_url_assembly():
    settings = Settings(
        _env_file=None,
        postgres_user="u",
        postgres_password="p",
        postgres_host="h",
        postgres_port=5555,
        postgres_db="d",
    )
    assert settings.database_url == "postgresql+psycopg://u:p@h:5555/d"


def test_defaults_are_local_dev():
    settings = Settings(_env_file=None)
    assert settings.postgres_host == "localhost"
    assert settings.s3_endpoint_url is not None
    assert settings.s3_endpoint_url.startswith("http://localhost")
    assert settings.postgres_sslmode is None


def test_database_url_includes_sslmode_when_set():
    settings = Settings(
        _env_file=None,
        postgres_user="u",
        postgres_password="p",
        postgres_host="h",
        postgres_port=5555,
        postgres_db="d",
        postgres_sslmode="require",
    )
    assert settings.database_url == "postgresql+psycopg://u:p@h:5555/d?sslmode=require"


def test_database_url_omits_sslmode_by_default():
    settings = Settings(_env_file=None, postgres_host="h")
    assert "sslmode" not in settings.database_url


def test_blank_s3_settings_in_the_environment_mean_unset(monkeypatch):
    # A server's .env says "use real S3 and the instance role" by leaving these BLANK;
    # an environment variable can only be a string, so blank has to be read as None.
    monkeypatch.setenv("S3_ENDPOINT_URL", "")
    monkeypatch.setenv("S3_ACCESS_KEY", "")
    monkeypatch.setenv("S3_SECRET_KEY", "   ")

    settings = Settings(_env_file=None)

    assert settings.s3_endpoint_url is None
    assert settings.s3_access_key is None
    assert settings.s3_secret_key is None


def test_blank_s3_settings_in_a_dotenv_file_mean_unset(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("S3_ENDPOINT_URL=\nS3_ACCESS_KEY=\nS3_SECRET_KEY=\n", encoding="utf-8")

    settings = Settings(_env_file=env_file)

    assert (settings.s3_endpoint_url, settings.s3_access_key, settings.s3_secret_key) == (
        None,
        None,
        None,
    )


def test_absent_s3_settings_still_default_to_local_minio(monkeypatch):
    # Local development must be unchanged: nothing set means MinIO.
    for name in ("S3_ENDPOINT_URL", "S3_ACCESS_KEY", "S3_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    assert settings.s3_endpoint_url == "http://localhost:9000"
    assert settings.s3_access_key == "slopadmin"


def test_nonblank_s3_settings_are_kept(monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://minio:9000")
    monkeypatch.setenv("S3_ACCESS_KEY", "abc")

    settings = Settings(_env_file=None)

    assert settings.s3_endpoint_url == "http://minio:9000"
    assert settings.s3_access_key == "abc"


def test_a_blank_s3_config_builds_a_client_for_real_aws_s3(monkeypatch):
    # The end result that matters on the server: a boto3 client aimed at the regional AWS
    # endpoint, with no explicit (MinIO) credentials overriding the default chain.
    from sloppy.storage import get_s3_client

    monkeypatch.setenv("S3_ENDPOINT_URL", "")
    monkeypatch.setenv("S3_ACCESS_KEY", "")
    monkeypatch.setenv("S3_SECRET_KEY", "")
    monkeypatch.setenv("AWS_REGION", "us-east-2")
    # no ambient credentials in the test, so the client builds without contacting AWS
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    # a throwaway default session, so this test neither reads nor leaves behind cached
    # credentials that other tests would then see
    monkeypatch.setattr(boto3, "DEFAULT_SESSION", None)

    client = get_s3_client(Settings(_env_file=None))

    assert client.meta.endpoint_url == "https://s3.us-east-2.amazonaws.com"
    assert client.meta.region_name == "us-east-2"


def test_s3_endpoint_url_can_be_unset_for_real_aws_s3():
    settings = Settings(_env_file=None, s3_endpoint_url=None)
    assert settings.s3_endpoint_url is None
    assert settings.aws_region == "us-east-1"


def test_active_model_defaults_to_unset_and_can_be_overridden():
    settings = Settings(_env_file=None)
    assert settings.active_model_name == ""
    assert settings.active_model_version == ""

    overridden = Settings(
        _env_file=None, active_model_name="xgboost", active_model_version="20260101-000000"
    )
    assert overridden.active_model_name == "xgboost"
    assert overridden.active_model_version == "20260101-000000"
