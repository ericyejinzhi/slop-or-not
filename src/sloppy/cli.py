import csv
import itertools
import sys
from pathlib import Path

import pandas as pd
import typer
from sqlalchemy import func

from sloppy import cli_ui
from sloppy.config import get_settings
from sloppy.db.models import Channel, Label, Thumbnail, Video, VideoScore
from sloppy.db.session import session_scope
from sloppy.features.dataset import assemble_dataset, load_splits
from sloppy.features.pipeline import compute_nlp_features, compute_vision_features
from sloppy.flows.refresh import refresh_all_tracked_channels_flow, refresh_channel_flow
from sloppy.ingest.pipeline import DEFAULT_SAMPLE_SIZE, DEFAULT_SAMPLE_WINDOW, ingest_channel
from sloppy.ingest.thumbnails import (
    download_thumbnail_bytes,
    extract_thumbnail_url,
    upload_thumbnail,
)
from sloppy.ingest.trim import trim_channel_to_sample
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
from sloppy.label.pool import (
    candidate_channel_batches,
    candidate_videos,
    consistency_sample,
    sample_channel_batches,
    sample_pool,
)
from sloppy.label.split import (
    assign_channels_to_splits,
    assign_videos_to_splits,
    canonical_labels,
    channel_stats,
)
from sloppy.models.ablation import format_ablation_table
from sloppy.models.cv import GROUP_BY_CHOICES, cross_validate
from sloppy.models.evaluate import BinaryMetrics, evaluate
from sloppy.models.report import top_errors
from sloppy.models.scores import upsert_video_score
from sloppy.models.tracking import finish, log_metrics, start_run
from sloppy.models.train import (
    FEATURE_GROUPS,
    MODEL_NAMES,
    save_model,
    score_dataframe,
    train_model,
)
from sloppy.storage import ensure_bucket, get_s3_client

app = typer.Typer(no_args_is_help=True, help="Slop-or-not: YouTube content quality classifier.")
ingest_app = typer.Typer(no_args_is_help=True, help="YouTube ingestion commands (Phase 1).")
label_app = typer.Typer(no_args_is_help=True, help="Labeling commands (Phase 2).")
model_app = typer.Typer(no_args_is_help=True, help="Baseline model commands (Phase 3).")
features_app = typer.Typer(no_args_is_help=True, help="NLP/vision feature commands (Phase 4).")
orchestrate_app = typer.Typer(no_args_is_help=True, help="Prefect flow triggers (Phase 7).")
app.add_typer(ingest_app, name="ingest")
app.add_typer(label_app, name="label")
app.add_typer(model_app, name="model")
app.add_typer(features_app, name="features")
app.add_typer(orchestrate_app, name="orchestrate")

DEFAULT_SEED_CSV = Path("data/seed_channels.csv")
DEFAULT_SPLITS_CSV = Path("data/splits.csv")
DEFAULT_MODEL_ARTIFACTS_DIR = Path("models_artifacts")


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
def run_channel_ingest(
    id_or_handle: str,
    max_videos: int | None = typer.Option(
        None,
        help="Only ingest the N most-recent videos (uploads playlist is most-recent-"
        "first). If set, this takes precedence over --sample-window/--sample-size "
        "below. Unset = sampled selection (the project's current default methodology).",
    ),
    sample_window: int = typer.Option(
        DEFAULT_SAMPLE_WINDOW,
        help="Ignored if --max-videos is set. Randomly sample from the N most-recent "
        "videos, instead of always taking the exact same most-recent ones - channel-"
        "batch labeling wants a representative sample, not just the latest uploads.",
    ),
    sample_size: int = typer.Option(
        DEFAULT_SAMPLE_SIZE,
        help="Ignored if --max-videos is set. How many videos to randomly sample.",
    ),
) -> None:
    """Ingest a channel end-to-end: videos, comments, thumbnails. Safe to re-run (upserts)."""
    settings = get_settings()
    if not settings.youtube_api_key:
        typer.secho("[FAIL] YOUTUBE_API_KEY is not set in .env", fg="red")
        raise typer.Exit(1)

    try:
        with cli_ui.spinner(f"Ingesting {id_or_handle}..."):
            if max_videos is not None:
                summary = ingest_channel(settings, id_or_handle, limit=max_videos)
            else:
                summary = ingest_channel(
                    settings,
                    id_or_handle,
                    sample_window=sample_window,
                    sample_size=sample_size,
                )
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


def _already_ingested_handles(session) -> set[str]:
    """Lowercased handles (as stored on `Channel.handle`, e.g. YouTube's `customUrl`,
    which is always lowercase regardless of how the handle was originally cased) for
    channels that have completed at least one full `ingest_channel` run - that function
    only sets `last_ingested_at` after successfully finishing, so this is a reliable
    "fully done before" signal, not just "exists in the DB at all".
    """
    rows = session.query(Channel.handle).filter(Channel.last_ingested_at.isnot(None)).all()
    return {handle.lower() for (handle,) in rows if handle}


@ingest_app.command("seed-channels")
def ingest_seed_channels(
    csv_path: Path = typer.Option(DEFAULT_SEED_CSV),  # noqa: B008
    limit: int | None = typer.Option(None, help="Only process the first N rows"),
    max_videos_per_channel: int | None = typer.Option(
        None,
        help="Only ingest the N most-recent videos per channel (uploads playlist is "
        "most-recent-first). If set, this takes precedence over --sample-window/"
        "--sample-size below. Unset = sampled selection (the project's current default "
        "methodology - channel-batch labeling wants a representative sample per "
        "channel, not always the exact same most-recent N).",
    ),
    sample_window: int = typer.Option(
        DEFAULT_SAMPLE_WINDOW,
        help="Ignored if --max-videos-per-channel is set. See `slop ingest channel --help`.",
    ),
    sample_size: int = typer.Option(
        DEFAULT_SAMPLE_SIZE,
        help="Ignored if --max-videos-per-channel is set. See `slop ingest channel --help`.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Re-ingest channels that have already completed a full ingest, instead of "
        "skipping them. Off by default so re-running the CSV after adding new rows only "
        "processes what's new.",
    ),
) -> None:
    """Bulk-ingest every channel in a seed_channels.csv (handle column). Skips channels
    that have already completed a full ingest, unless --force is passed. Tolerates
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

    done_handles: set[str] = set()
    if not force:
        with session_scope() as session:
            done_handles = _already_ingested_handles(session)

    successes = 0
    failures = 0
    skipped = 0
    with cli_ui.spinner("Starting ingestion...") as status:
        for row in rows:
            handle = (row.get("handle") or "").strip()
            if not handle:
                continue
            if handle.lower() in done_handles:
                cli_ui.skip(f"{handle}: already ingested (use --force to re-ingest)")
                skipped += 1
                continue
            status.update(f"Ingesting {handle} ({successes + failures + skipped + 1}/{len(rows)})")
            try:
                if max_videos_per_channel is not None:
                    summary = ingest_channel(settings, handle, limit=max_videos_per_channel)
                else:
                    summary = ingest_channel(
                        settings,
                        handle,
                        sample_window=sample_window,
                        sample_size=sample_size,
                    )
            except Exception as exc:
                cli_ui.fail(f"{handle}: {exc}")
                failures += 1
                continue
            successes += 1
            counts = (
                f"{summary.videos_upserted} videos, "
                f"{summary.comments_upserted} comments, "
                f"{summary.thumbnails_upserted} thumbnails"
            )
            if summary.errors:
                cli_ui.warn(f"{handle}: {counts} ({len(summary.errors)} issue(s))")
            else:
                cli_ui.ok(f"{handle}: {counts}")

    typer.secho(
        f"\n{successes} channel(s) ingested, {skipped} skipped, {failures} failed", bold=True
    )
    if successes == 0 and skipped == 0:
        raise typer.Exit(1)


@ingest_app.command("trim-channel")
def trim_channel(
    id_or_handle: str,
    keep: int = typer.Option(10, help="How many videos to randomly keep for this channel"),
    seed: int | None = typer.Option(None),
    yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt"),
) -> None:
    """Randomly trims an already-ingested channel down to `keep` videos, deleting the
    rest along with their comments/thumbnails (DB rows and the real S3/MinIO objects).
    Re-ingestable from YouTube later, but not free - confirms before deleting."""
    with session_scope() as session:
        channel = (
            session.query(Channel)
            .filter((Channel.id == id_or_handle) | (Channel.handle == id_or_handle))
            .first()
        )
        if channel is None:
            typer.secho(f"[FAIL] No ingested channel matching {id_or_handle!r}", fg="red")
            raise typer.Exit(1)
        channel_id = channel.id
        before = session.query(Video).filter(Video.channel_id == channel_id).count()

    if before <= keep:
        typer.echo(f"{id_or_handle}: already has {before} videos (<= {keep}), nothing to trim")
        return

    if not yes and not typer.confirm(
        f"Delete up to {before - keep} of {before} videos for {id_or_handle} (keeping {keep} - "
        "fewer may be deleted if more than that many are already labeled)?"
    ):
        typer.echo("Aborted.")
        raise typer.Exit(1)

    settings = get_settings()
    s3_client = get_s3_client(settings)
    with session_scope() as session:
        deleted = trim_channel_to_sample(session, s3_client, channel_id, keep=keep, seed=seed)

    typer.secho(f"{id_or_handle}: deleted {deleted} videos, kept {before - deleted}", bold=True)


@ingest_app.command("trim-all")
def trim_all(
    keep: int = typer.Option(10, help="How many videos to randomly keep per channel"),
    seed: int | None = typer.Option(None),
    yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt"),
) -> None:
    """Runs trim-channel's logic across every ingested channel in the DB. Confirms once,
    up front, with a total count - not per-channel."""
    with session_scope() as session:
        channel_rows = session.query(Channel.id, Channel.handle).all()
        counts = dict(
            session.query(Video.channel_id, func.count(Video.id)).group_by(Video.channel_id).all()
        )

    trimmable = [(cid, handle) for cid, handle in channel_rows if counts.get(cid, 0) > keep]
    if not trimmable:
        typer.echo(f"No channel has more than {keep} videos - nothing to trim.")
        return

    total_to_delete = sum(counts[cid] - keep for cid, _ in trimmable)
    if not yes and not typer.confirm(
        f"Delete up to {total_to_delete} videos total across {len(trimmable)} channel(s) "
        f"(keeping {keep} each - fewer may be deleted per channel if more than that many "
        "are already labeled)?"
    ):
        typer.echo("Aborted.")
        raise typer.Exit(1)

    settings = get_settings()
    s3_client = get_s3_client(settings)
    with cli_ui.spinner("Trimming...") as status:
        for channel_id, handle in trimmable:
            status.update(f"Trimming {handle or channel_id}")
            with session_scope() as session:
                deleted = trim_channel_to_sample(
                    session, s3_client, channel_id, keep=keep, seed=seed
                )
            cli_ui.ok(f"{handle or channel_id}: deleted {deleted} videos")

    typer.secho(
        f"\nDone - {total_to_delete} videos deleted across {len(trimmable)} channel(s)", bold=True
    )


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


def _display_video(s3_client, pool_video, video, thumbnail) -> None:
    """Shared by both labeling modes below - prints one video's info and opens its
    thumbnail, identical to what the web labeling page shows for the same video."""
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
                s3_client, video.id, thumbnail.s3_bucket, thumbnail.s3_key, thumbnail.content_type
            )
            open_image(path)
        except Exception as exc:
            typer.secho(f"  [warn] could not open thumbnail: {exc}", fg="yellow")
    else:
        typer.secho("  [warn] no thumbnail on record for this video", fg="yellow")


def _prompt_action() -> str:
    typer.echo("  [y]up  [n]down  [s]kip  [q]uit > ", nl=False)
    action = None
    while action is None:
        action = action_for_key(read_key())
    typer.echo(action)
    return action


@label_app.command("run")
def run_labeling(
    labeler: str | None = typer.Option(None, help="Defaults to LABELER_NAME in .env"),
    limit: int = typer.Option(50, help="Stop after this many videos labeled this session"),
    per_channel_max: int = typer.Option(30, help="Ignored for --mode channel"),
    pool_size: int = typer.Option(
        400, help="Candidate videos for pool mode, or candidate CHANNELS for channel mode"
    ),
    seed: int | None = typer.Option(None),
    mode: str = typer.Option(
        "channel",
        help="'channel' (label a whole channel's sampled batch at once - the project's "
        "current default methodology), 'pool' (one fresh video at a time), or "
        "'consistency' (relabel a past sample)",
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

    if mode == "channel":
        run_channel_batch_labeling(effective_labeler, limit, pool_size, seed)
        return

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
        typer.secho(
            f"[FAIL] --mode must be 'channel', 'pool', or 'consistency', got {mode!r}", fg="red"
        )
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

        _display_video(s3_client, pool_video, video, thumbnail)
        action = _prompt_action()
        if action == "quit":
            break

        with session_scope() as session:
            record_label(session, video_id=video.id, labeler=effective_labeler, label=action)
        labeled_count += 1

    typer.secho(f"\nLabeled {labeled_count} video(s) this session.", bold=True)


def run_channel_batch_labeling(
    effective_labeler: str, limit: int, pool_size: int, seed: int | None
) -> None:
    """`slop label run --mode channel` - the project's current default labeling
    methodology (see docs/writeups/TODO.md). One keypress labels every video in a
    channel's sampled batch at once, via the same candidate_channel_batches/
    sample_channel_batches pool functions the web labeling page's channel mode uses
    (src/sloppy/api/routers/labels.py's GET /labels/channel-pool).
    """
    settings = get_settings()
    with session_scope() as session:
        batches = candidate_channel_batches(session, exclude_labeled=True)
    batches = sample_channel_batches(batches, target_size=pool_size, seed=seed)

    if not batches:
        typer.secho("No channels available to label.", fg="yellow")
        raise typer.Exit(0)

    typer.secho(
        f"Labeling as '{effective_labeler}'. {len(batches)} channel(s) in this pool.", bold=True
    )
    typer.echo("Keys: y=up (quality)   n=down (slop)   s=skip   q=quit\n")

    s3_client = get_s3_client(settings)
    labeled_count = 0

    for batch in batches:
        if labeled_count >= limit:
            break

        typer.secho(f"\n=== {batch.channel_handle or batch.channel_id} ===", bold=True)
        videos_by_id = {}
        with session_scope() as session:
            for pool_video in batch.videos:
                video = session.get(Video, pool_video.video_id)
                thumbnail = session.get(Thumbnail, pool_video.video_id)
                if video is None:
                    continue
                videos_by_id[pool_video.video_id] = video
                _display_video(s3_client, pool_video, video, thumbnail)

        if not videos_by_id:
            continue

        typer.echo(f"\n  {len(videos_by_id)} video(s) shown above for this channel.")
        action = _prompt_action()
        if action == "quit":
            break

        with session_scope() as session:
            for video_id in videos_by_id:
                record_label(session, video_id=video_id, labeler=effective_labeler, label=action)
        labeled_count += len(videos_by_id)

    typer.secho(f"\nLabeled {labeled_count} video(s) this session.", bold=True)


@label_app.command("make-splits")
def make_splits(
    out_csv: Path = typer.Option(DEFAULT_SPLITS_CSV),  # noqa: B008
    proportions: str = typer.Option("0.70,0.15,0.15"),
    seed: int = typer.Option(42),
    group_by: str = typer.Option(
        "channel",
        help="'channel' (default): whole channels per split, so no channel spans train and "
        "test - the honest generalization check, and the right choice while labels are "
        "per channel. 'video': label-stratified random split by video, ignoring channels "
        "(a channel's videos can span train and test - inflates metrics).",
    ),
) -> None:
    """Write a stratified train/val/test split to a CSV artifact."""
    if group_by not in ("video", "channel"):
        typer.secho(f"[FAIL] --group-by must be 'video' or 'channel', got {group_by!r}", fg="red")
        raise typer.Exit(1)
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

    if group_by == "video":
        video_split = assign_videos_to_splits(canonical, proportions=parts, seed=seed)
    else:
        channel_split = assign_channels_to_splits(
            channel_stats(canonical), proportions=parts, seed=seed
        )
        video_split = {vid: channel_split[cid] for vid, (cid, _label) in canonical.items()}

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["video_id", "channel_id", "label", "split"])
        for video_id, (channel_id, label) in sorted(canonical.items()):
            writer.writerow([video_id, channel_id, label, video_split[video_id]])

    split_counts: dict[str, int] = {}
    down_counts: dict[str, int] = {}
    for video_id, (_channel_id, label) in canonical.items():
        split_name = video_split[video_id]
        split_counts[split_name] = split_counts.get(split_name, 0) + 1
        down_counts[split_name] = down_counts.get(split_name, 0) + (label == "down")

    typer.secho(f"Wrote {len(canonical)} labeled video(s) to {out_csv}", bold=True)
    for name in ("train", "val", "test"):
        total = split_counts.get(name, 0)
        down = down_counts.get(name, 0)
        share = f"{down / total:.0%}" if total else "n/a"
        typer.echo(f"  {name}: {total} ({down} down, {share})")


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


@model_app.command("train")
def train_command(
    model: str = typer.Option("both", help="'logistic_regression', 'xgboost', or 'both'"),
    splits_csv: Path = typer.Option(DEFAULT_SPLITS_CSV),  # noqa: B008
    artifacts_dir: Path = typer.Option(DEFAULT_MODEL_ARTIFACTS_DIR),  # noqa: B008
) -> None:
    """Train the baseline model(s) on data/splits.csv, persist the artifact, and score
    every labeled video into video_scores. Run `slop model evaluate` afterward to see
    metrics."""
    settings = get_settings()

    if model != "both" and model not in MODEL_NAMES:
        typer.secho(
            f"[FAIL] --model must be 'both' or one of {MODEL_NAMES}, got {model!r}", fg="red"
        )
        raise typer.Exit(1)

    if not splits_csv.exists():
        typer.secho(f"[FAIL] {splits_csv} not found - run `slop label make-splits` first", fg="red")
        raise typer.Exit(1)

    splits = load_splits(splits_csv)
    with session_scope() as session:
        df = assemble_dataset(session, splits)

    if df.empty:
        typer.secho("No labeled videos found in splits.csv - nothing to train on.", fg="yellow")
        raise typer.Exit(1)

    train_df = df[df["split"] == "train"]
    if train_df.empty:
        typer.secho("No rows in the train split - nothing to train on.", fg="red")
        raise typer.Exit(1)

    model_names = MODEL_NAMES if model == "both" else (model,)

    for model_name in model_names:
        typer.secho(f"Training {model_name} on {len(train_df)} row(s)...", bold=True)
        run = start_run(settings, config={"model_name": model_name, "train_rows": len(train_df)})

        trained = train_model(model_name, train_df)
        model_path = save_model(trained, artifacts_dir, train_row_count=len(train_df))
        typer.echo(f"  saved to {model_path}")

        scores = score_dataframe(trained, df)
        with session_scope() as session:
            for idx, row in df.iterrows():
                score = float(scores[idx])
                predicted_label = "down" if score >= 0.5 else "up"
                upsert_video_score(
                    session,
                    video_id=row["video_id"],
                    model_name=model_name,
                    model_version=trained.version,
                    score=score,
                    predicted_label=predicted_label,
                    split=row["split"],
                )
        typer.echo(f"  scored {len(df)} video(s), version={trained.version}")

        log_metrics(run, {"train_rows": len(train_df), "scored_rows": len(df)})
        finish(run)


def _print_metrics(label: str, m: BinaryMetrics) -> None:
    pr_auc = "nan" if pd.isna(m.pr_auc) else f"{m.pr_auc:.3f}"
    typer.echo(
        f"  {label}: n={m.n} pr_auc={pr_auc} f1={m.f1:.3f} tp={m.tp} fp={m.fp} tn={m.tn} fn={m.fn}"
    )


@model_app.command("cv")
def cv_command(
    model: str = typer.Option("both", help="'logistic_regression', 'xgboost', or 'both'"),
    folds: int = typer.Option(5, help="Number of folds (k)"),
    repeats: int = typer.Option(
        1,
        help="Repeat the whole k-fold with different channel partitions (seed + repeat). "
        "More repeats = steadier numbers, since there are only ~60 channels to partition.",
    ),
    seed: int = typer.Option(42),
    group_by: str = typer.Option(
        "channel",
        help="'channel' (default): StratifiedGroupKFold - each channel stays entirely in one "
        "fold, label ratio balanced across folds. 'video': plain StratifiedKFold, which "
        "leaks channel identity (only for measuring that gap).",
    ),
    feature_group: str = typer.Option(
        "all", help=f"Feature set: one of {', '.join(FEATURE_GROUPS)} (see `slop model ablation`)"
    ),
) -> None:
    """Stratified k-fold cross-validation over every non-skip labeled video, grouped by
    channel. Replaces a single noisy val/test split with k held-out folds, so the number
    reflects performance on channels the model never trained on. Reads labels and features
    straight from the database (no splits.csv) and writes nothing - no models are saved
    and video_scores is not touched."""
    if model != "both" and model not in MODEL_NAMES:
        typer.secho(
            f"[FAIL] --model must be 'both' or one of {MODEL_NAMES}, got {model!r}", fg="red"
        )
        raise typer.Exit(1)
    if group_by not in GROUP_BY_CHOICES:
        typer.secho(
            f"[FAIL] --group-by must be one of {GROUP_BY_CHOICES}, got {group_by!r}", fg="red"
        )
        raise typer.Exit(1)
    if feature_group not in FEATURE_GROUPS:
        typer.secho(
            f"[FAIL] --feature-group must be one of {tuple(FEATURE_GROUPS)}, got {feature_group!r}",
            fg="red",
        )
        raise typer.Exit(1)

    with session_scope() as session:
        canonical = canonical_labels(session)
        if not canonical:
            typer.secho("No non-skip labels found yet - nothing to cross-validate.", fg="yellow")
            raise typer.Exit(1)
        df = assemble_dataset(
            session,
            {vid: (channel_id, label, "cv") for vid, (channel_id, label) in canonical.items()},
        )

    numeric_features, categorical_features = FEATURE_GROUPS[feature_group]
    n_channels = df["channel_id"].nunique()
    typer.secho(
        f"{len(df)} labeled video(s) from {n_channels} channel(s); {folds}-fold x {repeats} "
        f"repeat(s), group_by={group_by}, features={feature_group}",
        bold=True,
    )

    model_names = MODEL_NAMES if model == "both" else (model,)
    for model_name in model_names:
        try:
            with cli_ui.spinner(f"Cross-validating {model_name}..."):
                result = cross_validate(
                    df,
                    model_name,
                    n_splits=folds,
                    seed=seed,
                    repeats=repeats,
                    group_by=group_by,
                    numeric_features=numeric_features,
                    categorical_features=categorical_features,
                )
        except ValueError as exc:
            cli_ui.fail(f"{model_name}: {exc}")
            raise typer.Exit(1) from exc

        typer.secho(f"\n{model_name}", bold=True)
        for fold in result.folds:
            _print_metrics(
                f"r{fold.repeat} fold {fold.fold} ({fold.n_test_channels} ch)",
                fold.report.overall,
            )

        typer.echo("  across folds (mean +/- std, [min, max]):")
        for row in result.summary().itertuples():
            typer.echo(
                f"    {row.who:<8} {row.metric:<6} {row.mean:.3f} +/- {row.std:.3f}  "
                f"[{row.min:.3f}, {row.max:.3f}]"
            )
        _print_metrics("pooled out-of-fold", result.pooled())


@model_app.command("evaluate")
def evaluate_command(
    model_name: str = typer.Option(..., help="e.g. 'logistic_regression' or 'xgboost'"),
    model_version: str = typer.Option(..., help="version string printed by `slop model train`"),
    split: str = typer.Option("val", help="'val' or 'test'"),
) -> None:
    """PR-AUC/F1/confusion-matrix metrics vs. the majority-class baseline, overall and
    per-channel (to catch channel-identity leakage)."""
    with session_scope() as session:
        canonical = canonical_labels(session)
        score_rows = (
            session.query(VideoScore.video_id, VideoScore.score, VideoScore.split)
            .filter(VideoScore.model_name == model_name, VideoScore.model_version == model_version)
            .all()
        )

    if not score_rows:
        typer.secho(f"[FAIL] No scores found for {model_name} version {model_version}", fg="red")
        raise typer.Exit(1)

    records = []
    for video_id, score, row_split in score_rows:
        if video_id not in canonical:
            continue
        channel_id, label = canonical[video_id]
        records.append(
            {
                "video_id": video_id,
                "channel_id": channel_id,
                "y": 1 if label == "down" else 0,
                "score": score,
                "split": row_split,
            }
        )

    df = pd.DataFrame.from_records(records)
    if df.empty:
        typer.secho("No scored videos with a canonical (non-skip) label found.", fg="yellow")
        raise typer.Exit(1)

    train_y = df[df["split"] == "train"]["y"]
    eval_df = df[df["split"] == split]
    if train_y.empty:
        typer.secho("[FAIL] No train-split rows found - can't compute majority baseline.", fg="red")
        raise typer.Exit(1)
    if eval_df.empty:
        typer.secho(f"No rows in the '{split}' split for this model/version.", fg="yellow")
        raise typer.Exit(1)

    report = evaluate(eval_df, train_y)

    typer.secho(f"Evaluation for {model_name} v{model_version} on '{split}' split:", bold=True)
    _print_metrics("model   ", report.overall)
    _print_metrics("baseline", report.majority_baseline)

    typer.echo("\nPer-channel:")
    for channel_id, metrics in sorted(report.per_channel.items()):
        _print_metrics(channel_id, metrics)


@model_app.command("report")
def report_command(
    model_name: str = typer.Option(..., help="e.g. 'logistic_regression' or 'xgboost'"),
    model_version: str = typer.Option(..., help="version string printed by `slop model train`"),
    split: str = typer.Option("test", help="'val' or 'test'"),
    n: int = typer.Option(20, help="how many of each error type to show"),
) -> None:
    """Top-N most confidently wrong predictions (false positives and false negatives) -
    the error-analysis step. See docs/writeups/phase-3 for why this is a CLI report
    rather than a notebook."""
    with session_scope() as session:
        canonical = canonical_labels(session)
        rows = (
            session.query(
                VideoScore.video_id,
                VideoScore.score,
                VideoScore.predicted_label,
                VideoScore.split,
                Video.title,
            )
            .join(Video, Video.id == VideoScore.video_id)
            .filter(
                VideoScore.model_name == model_name,
                VideoScore.model_version == model_version,
                VideoScore.split == split,
            )
            .all()
        )

    records = []
    for video_id, score, predicted_label, row_split, title in rows:
        if video_id not in canonical:
            continue
        channel_id, label = canonical[video_id]
        records.append(
            {
                "video_id": video_id,
                "channel_id": channel_id,
                "title": title,
                "y": 1 if label == "down" else 0,
                "score": score,
                "predicted_label": predicted_label,
                "split": row_split,
            }
        )

    df = pd.DataFrame.from_records(records)
    if df.empty:
        typer.secho(
            f"No scored, labeled videos found for {model_name} v{model_version} on '{split}'.",
            fg="yellow",
        )
        raise typer.Exit(1)

    def _print_table(title: str, errors: pd.DataFrame) -> None:
        typer.secho(f"\n{title} ({len(errors)}):", bold=True)
        if errors.empty:
            typer.echo("  (none)")
            return
        for _, row in errors.iterrows():
            typer.echo(f"  score={row['score']:.3f}  {row['title']!r}  ({row['channel_id']})")

    _print_table(
        "Top false positives (predicted down, actually up)", top_errors(df, "false_positive", n)
    )
    _print_table(
        "Top false negatives (predicted up, actually down)", top_errors(df, "false_negative", n)
    )


@features_app.command("compute-nlp")
def compute_nlp(
    video_id: str | None = typer.Option(None, help="Only process this one video"),
    channel_id: str | None = typer.Option(None, help="Only process this one channel"),
    limit: int | None = typer.Option(None, help="Only process the first N videos"),
    only_missing: bool = typer.Option(
        False, "--only-missing", help="Skip videos that already have NLP features"
    ),
) -> None:
    """Compute + persist sentiment, comment-topic, and title-intent NLP features
    (including embeddings) for ingested videos. Idempotent - re-running overwrites."""
    with cli_ui.spinner("Computing NLP features (model loading can take a while)..."):
        processed = compute_nlp_features(
            video_id=video_id, limit=limit, channel_id=channel_id, only_missing=only_missing
        )

    if not processed:
        typer.secho("No matching videos found.", fg="yellow")
        raise typer.Exit(1)

    for vid, comment_count in processed:
        typer.echo(f"  {vid}: {comment_count} comment(s) scored")

    typer.secho(f"Computed NLP features for {len(processed)} video(s).", bold=True)


@features_app.command("compute-vision")
def compute_vision(
    video_id: str | None = typer.Option(None, help="Only process this one video"),
    channel_id: str | None = typer.Option(None, help="Only process this one channel"),
    limit: int | None = typer.Option(None, help="Only process the first N videos"),
    only_missing: bool = typer.Option(
        False, "--only-missing", help="Skip videos that already have vision features"
    ),
) -> None:
    """Compute + persist CLIP thumbnail embeddings + zero-shot scores for ingested
    videos that have a thumbnail on record. Idempotent - re-running overwrites."""
    settings = get_settings()
    with cli_ui.spinner("Computing vision features (model loading can take a while)..."):
        processed = compute_vision_features(
            settings,
            video_id=video_id,
            limit=limit,
            channel_id=channel_id,
            only_missing=only_missing,
        )

    if not processed:
        typer.secho("No videos with a thumbnail on record found.", fg="yellow")
        raise typer.Exit(1)

    for vid in processed:
        typer.echo(f"  {vid}: embedded + scored")

    typer.secho(f"Computed vision features for {len(processed)} video(s).", bold=True)


@model_app.command("ablation")
def ablation_command(
    model: str = typer.Option("xgboost", help="which estimator to use for every feature group"),
    splits_csv: Path = typer.Option(DEFAULT_SPLITS_CSV),  # noqa: B008
    artifacts_dir: Path = typer.Option(DEFAULT_MODEL_ARTIFACTS_DIR),  # noqa: B008
    split: str = typer.Option("val", help="which split to evaluate each variant on"),
) -> None:
    """Train the same estimator on 3 cumulative feature groups (metadata / +text / all)
    and print a side-by-side comparison table. Each variant is persisted and scored
    under its own model_name (e.g. 'xgboost_metadata'), so `slop model evaluate`/`report`
    work unmodified against any of them afterward."""
    settings = get_settings()

    if model not in MODEL_NAMES:
        typer.secho(f"[FAIL] --model must be one of {MODEL_NAMES}, got {model!r}", fg="red")
        raise typer.Exit(1)
    if not splits_csv.exists():
        typer.secho(f"[FAIL] {splits_csv} not found - run `slop label make-splits` first", fg="red")
        raise typer.Exit(1)

    splits = load_splits(splits_csv)
    with session_scope() as session:
        df = assemble_dataset(session, splits)

    if df.empty:
        typer.secho("No labeled videos found in splits.csv - nothing to train on.", fg="yellow")
        raise typer.Exit(1)

    train_df = df[df["split"] == "train"]
    if train_df.empty:
        typer.secho("No rows in the train split - nothing to train on.", fg="red")
        raise typer.Exit(1)

    reports = {}
    for group_name, (numeric, categorical) in FEATURE_GROUPS.items():
        model_name = f"{model}_{group_name}"
        typer.secho(f"Training {model_name} on {len(train_df)} row(s)...", bold=True)

        run = start_run(settings, config={"model_name": model_name, "train_rows": len(train_df)})
        trained = train_model(
            model, train_df, numeric_features=numeric, categorical_features=categorical
        )
        model_path = save_model(trained, artifacts_dir, train_row_count=len(train_df))
        typer.echo(f"  saved to {model_path}")

        scores = score_dataframe(trained, df)
        with session_scope() as session:
            for idx, row in df.iterrows():
                score = float(scores[idx])
                predicted_label = "down" if score >= 0.5 else "up"
                upsert_video_score(
                    session,
                    video_id=row["video_id"],
                    model_name=model_name,
                    model_version=trained.version,
                    score=score,
                    predicted_label=predicted_label,
                    split=row["split"],
                )
        log_metrics(run, {"train_rows": len(train_df), "scored_rows": len(df)})
        finish(run)

        eval_df = df[df["split"] == split].copy()
        eval_df["score"] = scores[eval_df.index]
        reports[group_name] = evaluate(eval_df, train_df["y"])

    table = format_ablation_table(reports)
    typer.echo("\n" + table.to_string(index=False))


@orchestrate_app.command("refresh-channel")
def refresh_channel_command(id_or_handle: str) -> None:
    """Run the ingest -> features -> score flow for one channel, in-process (no Prefect
    server/worker needed - useful for manual testing; a deployment schedules this for
    real, unattended, daily runs)."""
    result = refresh_channel_flow(id_or_handle)
    typer.secho(f"channel_id={result['channel_id']}", bold=True)
    typer.echo(f"  nlp_processed={result['nlp_processed']}")
    typer.echo(f"  vision_processed={result['vision_processed']}")
    typer.echo(f"  scored={result['scored']}")


@orchestrate_app.command("refresh-all")
def refresh_all_command(
    seed_channels_csv: Path = typer.Option(DEFAULT_SEED_CSV),  # noqa: B008
) -> None:
    """Run the ingest -> features -> score flow for every channel in
    data/seed_channels.csv, in-process, one after another."""
    results = refresh_all_tracked_channels_flow(seed_channels_csv=seed_channels_csv)
    if not results:
        typer.secho(f"No tracked channels found in {seed_channels_csv}.", fg="yellow")
        raise typer.Exit(1)
    for result in results:
        typer.echo(
            f"  {result['channel_id']}: nlp={result['nlp_processed']} "
            f"vision={result['vision_processed']} scored={result['scored']}"
        )
    typer.secho(f"Refreshed {len(results)} channel(s).", bold=True)


@orchestrate_app.command("serve")
def serve_command(
    cron: str = typer.Option("0 6 * * *", help="Cron expression for the daily refresh"),
) -> None:
    """Block and serve refresh-all-tracked-channels on a cron schedule - leave this
    running (its own terminal, or a background process) for real, unattended, scheduled
    refreshes. Set PREFECT_API_URL to the docker-compose server first, or the schedule
    and flow-run history land in a throwaway ephemeral server instead."""
    refresh_all_tracked_channels_flow.serve(name="daily-tracked-channels-refresh", cron=cron)


if __name__ == "__main__":
    app()
