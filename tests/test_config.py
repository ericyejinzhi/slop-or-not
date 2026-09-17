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
    assert settings.s3_endpoint_url.startswith("http://localhost")
