import itertools
import sys

import typer

from sloppy.config import get_settings
from sloppy.ingest.thumbnails import (
    download_thumbnail_bytes,
    extract_thumbnail_url,
    upload_thumbnail,
)
from sloppy.ingest.youtube import (
    fetch_top_comments,
    fetch_videos_metadata,
    get_youtube_client,
    iter_playlist_video_ids,
    resolve_channel,
)
from sloppy.storage import ensure_bucket, get_s3_client

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


@ingest_app.command("inspect-video")
def inspect_video(video_id: str) -> None:
    """Print a video's metadata plus its top 5 comments. No DB writes."""
    settings = get_settings()
    if not settings.youtube_api_key:
        typer.secho("[FAIL] YOUTUBE_API_KEY is not set in .env", fg="red")
        raise typer.Exit(1)

    client = get_youtube_client(settings)
    videos = fetch_videos_metadata(client, [video_id])
    if not videos:
        typer.secho(f"[FAIL] No video found for id {video_id!r}", fg="red")
        raise typer.Exit(1)
    video = videos[0]

    typer.secho(f"{video.title!r} ({video.id})", bold=True)
    typer.echo(f"  duration:  {video.duration_seconds}s")
    typer.echo(
        f"  views/likes/comments:  {video.view_count}/{video.like_count}/{video.comment_count}"
    )

    comments = fetch_top_comments(client, video_id, limit=5)
    typer.echo("\nTop comments:")
    if not comments:
        typer.echo("  (none — comments may be disabled, or there are none yet)")
    for comment in comments:
        preview = comment.text.replace("\n", " ")[:80]
        typer.echo(f"  - {comment.author_display_name} ({comment.like_count} likes): {preview}")


@ingest_app.command("inspect-thumbnail")
def inspect_thumbnail(video_id: str) -> None:
    """Extract, download, and upload a video's thumbnail to MinIO. No DB writes."""
    settings = get_settings()

    try:
        thumb_info = extract_thumbnail_url(video_id)
    except ValueError as exc:
        typer.secho(f"[FAIL] {exc}", fg="red")
        raise typer.Exit(1) from exc

    content, content_type = download_thumbnail_bytes(thumb_info.url)

    s3_client = get_s3_client(settings)
    ensure_bucket(s3_client, settings.s3_bucket_thumbnails)
    key = upload_thumbnail(s3_client, settings, video_id, content, content_type)

    typer.secho(f"Uploaded thumbnail for {video_id}", bold=True)
    typer.echo(f"  source url:    {thumb_info.url}")
    typer.echo(f"  dimensions:    {thumb_info.width}x{thumb_info.height}")
    typer.echo(f"  content-type:  {content_type}")
    typer.echo(f"  size:          {len(content)} bytes")
    typer.echo(f"  s3 bucket/key: {settings.s3_bucket_thumbnails}/{key}")


if __name__ == "__main__":
    app()
