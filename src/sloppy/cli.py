import sys

import typer

from sloppy.config import get_settings

app = typer.Typer(no_args_is_help=True, help="Slop-or-not: YouTube content quality classifier.")


@app.callback()
def main() -> None:
    """Slop-or-not command line tools."""


@app.command()
def smoke() -> None:
    """Verify Postgres (+pgvector) and MinIO are reachable and working."""
    settings = get_settings()
    failures = 0

    # --- Postgres + pgvector ---
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(settings.database_url)
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version()")).scalar_one()
            has_vector = conn.execute(
                text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'")
            ).scalar_one()
        typer.secho(f"[ok] Postgres reachable: {version.split(',')[0]}", fg="green")
        if has_vector:
            typer.secho("[ok] pgvector extension installed", fg="green")
        else:
            typer.secho("[FAIL] pgvector extension missing (recreate the volume?)", fg="red")
            failures += 1
    except Exception as exc:
        typer.secho(f"[FAIL] Postgres: {exc}", fg="red")
        failures += 1

    # --- MinIO put/get roundtrip ---
    try:
        from sloppy.storage import ensure_bucket, get_s3_client

        client = get_s3_client(settings)
        ensure_bucket(client, settings.s3_bucket_thumbnails)
        payload = b"slop-or-not smoke test"
        client.put_object(Bucket=settings.s3_bucket_thumbnails, Key="_smoke", Body=payload)
        got = client.get_object(Bucket=settings.s3_bucket_thumbnails, Key="_smoke")["Body"].read()
        client.delete_object(Bucket=settings.s3_bucket_thumbnails, Key="_smoke")
        if got == payload:
            typer.secho(
                f"[ok] MinIO put/get roundtrip in bucket '{settings.s3_bucket_thumbnails}'",
                fg="green",
            )
        else:
            typer.secho("[FAIL] MinIO roundtrip returned wrong bytes", fg="red")
            failures += 1
    except Exception as exc:
        typer.secho(f"[FAIL] MinIO: {exc}", fg="red")
        failures += 1

    if failures:
        typer.secho(f"{failures} check(s) failed — is `docker compose up -d` running?", fg="red")
        sys.exit(1)
    typer.secho("All smoke checks passed.", fg="green", bold=True)


if __name__ == "__main__":
    app()
