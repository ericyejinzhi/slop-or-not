from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # PostgreSQL
    postgres_user: str = "slop"
    postgres_password: str = "slop_dev_password"
    postgres_db: str = "slopornot"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # Object storage (MinIO locally, S3 in production — same API)
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "slopadmin"
    s3_secret_key: str = "slop_dev_password"
    s3_bucket_thumbnails: str = "thumbnails"

    # YouTube Data API v3
    youtube_api_key: str = ""

    # Labeling (Phase 2)
    labeler_name: str = ""

    # Model training (Phase 3). W&B tracking is best-effort: training works fully with
    # this blank - see sloppy.models.tracking.
    wandb_api_key: str = ""
    wandb_project: str = "slop-or-not"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
