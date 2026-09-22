import itertools
import sys

import typer

from sloppy.config import get_settings
from sloppy.ingest.youtube import (
    fetch_videos_metadata,
    get_youtube_client,
    iter_playlist_video_ids,
    resolve_channel,
)

app = typer.Typer(no_args_is_help=True, help="Slop-or-not: YouTube content quality classifier.")
ingest_app = typer.Typer(no_args_is_help=True, help="YouTube ingestion commands (Phase 1).")
app.add_typer(ingest_app, name="ingest")


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


@ingest_app.command("inspect-channel")
def inspect_channel(id_or_handle: str) -> None:
    """Resolve a channel, print metadata plus ~5 recent uploads. No DB/MinIO writes."""
    settings = get_settings()
    if not settings.youtube_api_key:
        typer.secho("[FAIL] YOUTUBE_API_KEY is not set in .env", fg="red")
        raise typer.Exit(1)

    client = get_youtube_client(settings)
    try:
        channel = resolve_channel(client, id_or_handle)
    except ValueError as exc:
        typer.secho(f"[FAIL] {exc}", fg="red")
        raise typer.Exit(1) from exc

    typer.secho(f"{channel.title} ({channel.id})", bold=True)
    typer.echo(f"  handle:            {channel.handle}")
    typer.echo(f"  subscribers:       {channel.subscriber_count}")
    typer.echo(f"  videos:            {channel.video_count}")
    typer.echo(f"  uploads playlist:  {channel.uploads_playlist_id}")

    video_ids = list(
        itertools.islice(iter_playlist_video_ids(client, channel.uploads_playlist_id), 5)
    )
    videos = fetch_videos_metadata(client, video_ids)

    typer.echo("\nRecent uploads:")
    for video in videos:
        topics = ", ".join(t.rsplit("/", 1)[-1] for t in video.topic_categories) or "-"
        typer.echo(f"  - {video.title!r}  [{video.duration_seconds}s]  topics: {topics}")


if __name__ == "__main__":
    app()
