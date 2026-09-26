import csv
import itertools
import sys
from pathlib import Path

import typer
from sqlalchemy import func

from sloppy.config import get_settings
from sloppy.db.models import Channel, Label, Thumbnail, Video
from sloppy.db.session import session_scope
from sloppy.ingest.pipeline import ingest_channel
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
from sloppy.label.display import cache_thumbnail, open_image
from sloppy.label.keyboard import action_for_key, read_key
from sloppy.label.labels import record_label
from sloppy.label.pool import candidate_videos, consistency_sample, sample_pool
from sloppy.label.split import assign_channels_to_splits, canonical_labels, channel_stats
from sloppy.storage import ensure_bucket, get_s3_client

app = typer.Typer(no_args_is_help=True, help="Slop-or-not: YouTube content quality classifier.")
ingest_app = typer.Typer(no_args_is_help=True, help="YouTube ingestion commands (Phase 1).")
label_app = typer.Typer(no_args_is_help=True, help="Labeling commands (Phase 2).")
app.add_typer(ingest_app, name="ingest")
app.add_typer(label_app, name="label")

DEFAULT_SEED_CSV = Path("data/seed_channels.csv")
DEFAULT_SPLITS_CSV = Path("data/splits.csv")


def _normalize_handle(handle: str) -> str:
    return handle.strip().lstrip("@").lower()


def _read_csv_rows(csv_path: Path) -> list[dict]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


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


@ingest_app.command("channel")
def run_channel_ingest(id_or_handle: str) -> None:
    """Ingest a channel end-to-end: videos, comments, thumbnails. Safe to re-run (upserts)."""
    settings = get_settings()
    if not settings.youtube_api_key:
        typer.secho("[FAIL] YOUTUBE_API_KEY is not set in .env", fg="red")
        raise typer.Exit(1)

    try:
        summary = ingest_channel(settings, id_or_handle)
    except ValueError as exc:
        typer.secho(f"[FAIL] {exc}", fg="red")
        raise typer.Exit(1) from exc

    typer.secho(f"Ingested channel {summary.channel_id}", bold=True)
    typer.echo(f"  videos upserted:     {summary.videos_upserted}")
    typer.echo(f"  comments upserted:   {summary.comments_upserted}")
    typer.echo(f"  thumbnails upserted: {summary.thumbnails_upserted}")
    if summary.errors:
        typer.secho(f"\n{len(summary.errors)} issue(s):", fg="yellow")
        for err in summary.errors:
            typer.echo(f"  - {err}")


@ingest_app.command("seed-channels")
def ingest_seed_channels(
    csv_path: Path = typer.Option(DEFAULT_SEED_CSV),  # noqa: B008
    limit: int | None = typer.Option(None, help="Only process the first N rows"),
) -> None:
    """Bulk-ingest every channel in a seed_channels.csv (handle column). Tolerates
    per-channel failures - one bad row does not abort the rest."""
    settings = get_settings()
    if not settings.youtube_api_key:
        typer.secho("[FAIL] YOUTUBE_API_KEY is not set in .env", fg="red")
        raise typer.Exit(1)

    rows = _read_csv_rows(csv_path)
    if limit is not None:
        rows = rows[:limit]
    if not rows:
        typer.secho(f"No rows found in {csv_path}", fg="yellow")
        raise typer.Exit(1)

    successes = 0
    failures = 0
    for row in rows:
        handle = (row.get("handle") or "").strip()
        if not handle:
            continue
        try:
            summary = ingest_channel(settings, handle)
        except Exception as exc:
            typer.secho(f"[FAIL] {handle}: {exc}", fg="red")
            failures += 1
            continue
        successes += 1
        issue_note = f" ({len(summary.errors)} issue(s))" if summary.errors else ""
        typer.echo(
            f"[ok] {handle}: {summary.videos_upserted} videos, "
            f"{summary.comments_upserted} comments, "
            f"{summary.thumbnails_upserted} thumbnails{issue_note}"
        )

    typer.secho(f"\n{successes} channel(s) ingested, {failures} failed", bold=True)
    if successes == 0:
        raise typer.Exit(1)


@label_app.command("seed-status")
def seed_status(csv_path: Path = typer.Option(DEFAULT_SEED_CSV)) -> None:  # noqa: B008
    """Cross-reference seed_channels.csv against ingested channels; flag thin channels."""
    rows = _read_csv_rows(csv_path)
    if not rows:
        typer.secho(f"No rows found in {csv_path}", fg="yellow")
        raise typer.Exit(1)

    with session_scope() as session:
        channels_by_handle = {
            _normalize_handle(c.handle): c
            for c in session.query(Channel).all()
            if c.handle is not None
        }
        video_counts = dict(
            session.query(Video.channel_id, func.count(Video.id)).group_by(Video.channel_id).all()
        )

        for row in rows:
            handle = (row.get("handle") or "").strip()
            if not handle:
                continue
            channel = channels_by_handle.get(_normalize_handle(handle))
            if channel is None:
                typer.secho(f"[missing] {handle}: not ingested", fg="red")
                continue
            count = video_counts.get(channel.id, 0)
            if count < 15:
                typer.secho(
                    f"[thin]    {handle}: {count} videos (below the 15-video floor)", fg="yellow"
                )
            else:
                typer.secho(f"[ok]      {handle}: {count} videos", fg="green")


@label_app.command("pool-preview")
def pool_preview(
    per_channel_max: int = typer.Option(30),
    target_size: int = typer.Option(400),
    seed: int | None = typer.Option(None),
    seed_csv: Path = typer.Option(DEFAULT_SEED_CSV),  # noqa: B008
) -> None:
    """Preview the labeling pool's composition (per-channel/per-genre) without starting
    interactive labeling."""
    genre_by_handle: dict[str, str] = {}
    if seed_csv.exists():
        for row in _read_csv_rows(seed_csv):
            handle = (row.get("handle") or "").strip()
            if handle:
                genre_by_handle[_normalize_handle(handle)] = (row.get("genre") or "").strip()

    with session_scope() as session:
        before = candidate_videos(session, per_channel_max=per_channel_max, exclude_labeled=False)
        after = candidate_videos(session, per_channel_max=per_channel_max, exclude_labeled=True)
        video_counts = dict(
            session.query(Video.channel_id, func.count(Video.id)).group_by(Video.channel_id).all()
        )

    sampled = sample_pool(after, target_size=target_size, seed=seed)

    typer.secho(
        f"Candidates before exclusion: {len(before)}  "
        f"after excluding labeled: {len(after)}  "
        f"sampled pool: {len(sampled)}",
        bold=True,
    )

    handle_by_channel = {v.channel_id: v.channel_handle for v in sampled}
    per_channel: dict[str, int] = {}
    for v in sampled:
        per_channel[v.channel_id] = per_channel.get(v.channel_id, 0) + 1

    typer.echo("\nPer-channel counts:")
    for channel_id, count in sorted(per_channel.items(), key=lambda kv: -kv[1]):
        handle = handle_by_channel.get(channel_id)
        total_videos = video_counts.get(channel_id, 0)
        warn = f"  [WARN: only {total_videos} total ingested videos]" if total_videos < 15 else ""
        typer.echo(f"  {handle or channel_id}: {count}{warn}")

    per_genre: dict[str, int] = {}
    for v in sampled:
        genre = genre_by_handle.get(_normalize_handle(v.channel_handle or ""), "") or "unknown"
        per_genre[genre] = per_genre.get(genre, 0) + 1

    typer.echo("\nPer-genre counts:")
    for genre, count in sorted(per_genre.items(), key=lambda kv: -kv[1]):
        typer.echo(f"  {genre}: {count}")


@label_app.command("run")
def run_labeling(
    labeler: str | None = typer.Option(None, help="Defaults to LABELER_NAME in .env"),
    limit: int = typer.Option(50, help="Stop after this many labels this session"),
    per_channel_max: int = typer.Option(30),
    pool_size: int = typer.Option(400),
    seed: int | None = typer.Option(None),
    mode: str = typer.Option(
        "pool", help="'pool' (fresh videos) or 'consistency' (relabel a past sample)"
    ),
    consistency_sample_size: int = typer.Option(20),
) -> None:
    """Interactive keyboard-driven labeling: y=up (quality), n=down (slop), s=skip, q=quit."""
    settings = get_settings()
    effective_labeler = labeler or settings.labeler_name
    if not effective_labeler:
        typer.secho(
            "[FAIL] No labeler identity - set LABELER_NAME in .env or pass --labeler", fg="red"
        )
        raise typer.Exit(1)

    if mode == "consistency":
        with session_scope() as session:
            pool = consistency_sample(session, n=consistency_sample_size, seed=seed)
    elif mode == "pool":
        with session_scope() as session:
            candidates = candidate_videos(
                session, per_channel_max=per_channel_max, exclude_labeled=True
            )
        pool = sample_pool(candidates, target_size=pool_size, seed=seed)
    else:
        typer.secho(f"[FAIL] --mode must be 'pool' or 'consistency', got {mode!r}", fg="red")
        raise typer.Exit(1)

    if not pool:
        typer.secho("No videos available for this mode.", fg="yellow")
        raise typer.Exit(0)

    typer.secho(f"Labeling as '{effective_labeler}'. {len(pool)} video(s) in this pool.", bold=True)
    typer.echo("Keys: y=up (quality)   n=down (slop)   s=skip   q=quit\n")

    s3_client = get_s3_client(settings)
    labeled_count = 0

    for pool_video in pool:
        if labeled_count >= limit:
            break

        with session_scope() as session:
            video = session.get(Video, pool_video.video_id)
            thumbnail = session.get(Thumbnail, pool_video.video_id)

        if video is None:
            continue

        typer.secho(f"\n{video.title!r}", bold=True)
        typer.echo(f"  channel:   {pool_video.channel_handle or pool_video.channel_id}")
        typer.echo(f"  published: {video.published_at}")
        typer.echo(f"  duration:  {video.duration_seconds}s")
        typer.echo(
            f"  views/likes/comments: {video.view_count}/{video.like_count}/{video.comment_count}"
        )

        if thumbnail is not None:
            try:
                path = cache_thumbnail(
                    s3_client,
                    video.id,
                    thumbnail.s3_bucket,
                    thumbnail.s3_key,
                    thumbnail.content_type,
                )
                open_image(path)
            except Exception as exc:
                typer.secho(f"  [warn] could not open thumbnail: {exc}", fg="yellow")
        else:
            typer.secho("  [warn] no thumbnail on record for this video", fg="yellow")

        typer.echo("  [y]up  [n]down  [s]kip  [q]uit > ", nl=False)
        action = None
        while action is None:
            action = action_for_key(read_key())
        typer.echo(action)

        if action == "quit":
            break

        with session_scope() as session:
            record_label(session, video_id=video.id, labeler=effective_labeler, label=action)
        labeled_count += 1

    typer.secho(f"\nLabeled {labeled_count} video(s) this session.", bold=True)


@label_app.command("make-splits")
def make_splits(
    out_csv: Path = typer.Option(DEFAULT_SPLITS_CSV),  # noqa: B008
    proportions: str = typer.Option("0.70,0.15,0.15"),
    seed: int = typer.Option(42),
) -> None:
    """Write a channel-grouped, stratified train/val/test split to a CSV artifact."""
    parts = tuple(float(p) for p in proportions.split(","))
    if len(parts) != 3 or abs(sum(parts) - 1.0) > 1e-6:
        typer.secho(
            f"[FAIL] --proportions must be 3 comma-separated floats summing to 1.0, "
            f"got {proportions!r}",
            fg="red",
        )
        raise typer.Exit(1)

    with session_scope() as session:
        canonical = canonical_labels(session)

    if not canonical:
        typer.secho("No non-skip labels found yet - nothing to split.", fg="yellow")
        raise typer.Exit(1)

    stats = channel_stats(canonical)
    channel_split = assign_channels_to_splits(stats, proportions=parts, seed=seed)

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["video_id", "channel_id", "label", "split"])
        for video_id, (channel_id, label) in sorted(canonical.items()):
            writer.writerow([video_id, channel_id, label, channel_split[channel_id]])

    split_counts: dict[str, int] = {}
    for channel_id, _label in canonical.values():
        split_name = channel_split[channel_id]
        split_counts[split_name] = split_counts.get(split_name, 0) + 1

    typer.secho(f"Wrote {len(canonical)} labeled video(s) to {out_csv}", bold=True)
    for name in ("train", "val", "test"):
        typer.echo(f"  {name}: {split_counts.get(name, 0)}")


@label_app.command("stats")
def label_stats() -> None:
    """Label distribution, minority-class share, per-channel counts, and relabel
    agreement rates (the roadmap's own "verify" bullet)."""
    with session_scope() as session:
        rows = (
            session.query(Label.video_id, Label.label, Label.created_at)
            .order_by(Label.video_id, Label.created_at)
            .all()
        )
        channel_by_video = dict(session.query(Video.id, Video.channel_id).all())

    if not rows:
        typer.secho("No labels recorded yet.", fg="yellow")
        raise typer.Exit(0)

    overall_counts = {"up": 0, "down": 0, "skip": 0}
    for row in rows:
        overall_counts[row.label] += 1

    typer.secho("Overall label counts:", bold=True)
    for label_value in ("up", "down", "skip"):
        typer.echo(f"  {label_value}: {overall_counts[label_value]}")

    non_skip_total = overall_counts["up"] + overall_counts["down"]
    if non_skip_total:
        minority_share = min(overall_counts["up"], overall_counts["down"]) / non_skip_total
        below_floor = minority_share < 0.25
        typer.secho(
            f"  minority-class share: {minority_share:.1%}"
            + (" [WARN: below the 25% floor]" if below_floor else ""),
            fg="red" if below_floor else "green",
        )

    per_channel: dict[str, dict[str, int]] = {}
    for row in rows:
        channel_id = channel_by_video.get(row.video_id, "unknown")
        counts = per_channel.setdefault(channel_id, {"up": 0, "down": 0, "skip": 0})
        counts[row.label] += 1

    typer.echo("\nPer-channel counts:")
    for channel_id, counts in sorted(per_channel.items()):
        typer.echo(f"  {channel_id}: up={counts['up']} down={counts['down']} skip={counts['skip']}")

    by_video: dict[str, list[str]] = {}
    for row in rows:
        if row.label == "skip":
            continue
        by_video.setdefault(row.video_id, []).append(row.label)

    relabeled = {vid: labels for vid, labels in by_video.items() if len(labels) >= 2}
    typer.echo()
    if relabeled:
        agree = sum(1 for labels in relabeled.values() if len(set(labels)) == 1)
        typer.echo(
            f"Consistency check: {len(relabeled)} video(s) relabeled, "
            f"{agree}/{len(relabeled)} agree ({agree / len(relabeled):.1%})"
        )
    else:
        typer.echo("Consistency check: no videos have been relabeled yet.")


if __name__ == "__main__":
    app()
