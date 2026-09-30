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
