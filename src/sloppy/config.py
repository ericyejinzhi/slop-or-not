from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # PostgreSQL. postgres_sslmode is None for local Docker Postgres (no TLS configured
    # there); set to "require" (or stricter, e.g. "verify-full") for RDS in production -
    # see docs/writeups/phase-8 for the full RDS migration notes.
    postgres_user: str = "slop"
    postgres_password: str = "slop_dev_password"
    postgres_db: str = "slopornot"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_sslmode: str | None = None

    # Object storage (MinIO locally, S3 in production - same boto3 API). s3_endpoint_url
    # is None for real AWS S3 (boto3 resolves the correct regional endpoint itself) -
    # set it only for MinIO or another S3-compatible service that needs an explicit
    # custom endpoint. aws_region matters for both real S3 (bucket region) and presigned
    # URL signing (Phase 8).
    # s3_access_key/secret are None-able too: a real EC2 deployment should leave these
    # unset and grant S3 access via an IAM instance role instead of a long-lived key
    # pair - boto3's default credential chain picks up an instance role automatically,
    # but only if explicit credentials aren't passed at all (not even blank ones).
    s3_endpoint_url: str | None = "http://localhost:9000"
    s3_access_key: str | None = "slopadmin"
    s3_secret_key: str | None = "slop_dev_password"
    s3_bucket_thumbnails: str = "thumbnails"
    aws_region: str = "us-east-1"

    # YouTube Data API v3
    youtube_api_key: str = ""

    # Labeling (Phase 2)
    labeler_name: str = ""

    # Model training (Phase 3). W&B tracking is best-effort: training works fully with
    # this blank - see sloppy.models.tracking.
    wandb_api_key: str = ""
    wandb_project: str = "slop-or-not"

    # Active model (Phase 5). Blank means unset - the API then shows null scores rather
    # than erroring. Set after promoting a trained model - see docs/writeups/TODO.md.
    active_model_name: str = ""
    active_model_version: str = ""

    # Model artifacts in object storage (Phase 8 prep). Trained models live in
    # `models_artifacts/` locally, which is not in git; a fresh server needs them from
    # somewhere. `slop model publish` uploads a model to s3_bucket_models, and with
    # fetch_model_from_s3 on, the active model is downloaded on demand when it is not
    # already on disk. Off by default so local development never touches the network
    # for this. The bucket must stay private and write-restricted: model.joblib is a
    # pickle, and loading a pickle from a bucket an attacker can write to means running
    # their code.
    s3_bucket_models: str = "models"
    fetch_model_from_s3: bool = False

    # Read-only deployment (Phase 8 prep). When true the API rejects every request that is
    # not a GET/HEAD/OPTIONS with a 403, so a public deployment cannot be used to ingest
    # channels (burning YouTube quota and CPU) or to write labels. Reading stays open.
    read_only: bool = False

    @property
    def database_url(self) -> str:
        base = (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
        if self.postgres_sslmode:
            base += f"?sslmode={self.postgres_sslmode}"
        return base


@lru_cache
def get_settings() -> Settings:
    return Settings()
