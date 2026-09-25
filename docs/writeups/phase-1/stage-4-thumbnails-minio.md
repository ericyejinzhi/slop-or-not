# Phase 1, Stage 4 - yt-dlp thumbnail extraction → MinIO

## What is being implemented

Thumbnail extraction and upload, independent of the YouTube Data API (no API key needed - yt-dlp reads the public watch page directly). Still no DB writes; this stage's `thumbnails` DB row happens in Stage 5.

New file: `src/sloppy/ingest/thumbnails.py`:
- `extract_thumbnail_url(video_id)` - uses `yt_dlp.YoutubeDL({"skip_download": True, ...})` to pull the video's thumbnail list without downloading any video/audio, then picks the highest-resolution entry (`_pick_best_thumbnail`, by width×height).
- `download_thumbnail_bytes(url)` - a plain `urllib.request.urlopen` GET, returns `(bytes, content_type)` read from the response's actual `Content-Type` header (not guessed from the URL).
- `upload_thumbnail(s3_client, settings, video_id, content, content_type)` - `put_object`s into the `thumbnails` bucket under the key `{video_id}.jpg`.

CLI: `slop ingest inspect-thumbnail <video_id>` - runs the full extract → download → upload chain and prints the result. New dependency: `yt-dlp`.

## What it should look like

```
$ uv run slop ingest inspect-thumbnail dQw4w9WgXcQ
Uploaded thumbnail for dQw4w9WgXcQ
  source url:    https://i.ytimg.com/vi_webp/dQw4w9WgXcQ/maxresdefault.webp
  dimensions:    1920x1080
  content-type:  image/webp
  size:          28620 bytes
  s3 bucket/key: thumbnails/dQw4w9WgXcQ.jpg
```

This was actually run against a real video (`dQw4w9WgXcQ`) in this environment - no API key required for this stage - and the object was confirmed present in the `thumbnails` bucket via a direct `list_objects_v2` call (`dQw4w9WgXcQ.jpg`, 28620 bytes). You should be able to see it in the MinIO console too: http://localhost:9001 → buckets → `thumbnails`.

## What to look out for - a real naming inconsistency, found during testing

**The plan's `{video_id}.jpg` key scheme doesn't always match the actual file format.** The test run above is a live example: YouTube's highest-resolution thumbnail for that video was served as `maxresdefault.webp` - an actual WebP image - but it still got uploaded under the key `dQw4w9WgXcQ.jpg`. The `content_type` stored alongside it (`image/webp`) is correct, so nothing is functionally broken (browsers and image libraries like PIL read the real format from the file's magic bytes or the `Content-Type` header, not the key's extension), but if you ever browse the MinIO console expecting `.jpg` to mean JPEG, some of these will surprise you.

This was a known trade-off in the approved plan (flat `{video_id}.jpg`, "the bucket itself is the namespace"), and I kept the implementation as approved rather than silently changing it. If you'd rather the key extension matched the real format (e.g. `{video_id}.webp` when yt-dlp gives back WebP), say so and I'll adjust `upload_thumbnail` to derive the extension from `content_type` before Stage 5 writes the corresponding DB rows - cheap to change now, more annoying once 200+ real rows depend on the naming.

Other things to note:
- `extract_thumbnail_url` filters out thumbnail entries that don't report `width`/`height` (some yt-dlp thumbnail entries are placeholder/storyboard tiles without dimensions) before picking the largest by area.
- `put_object` unconditionally overwrites, so re-running `inspect-thumbnail` (or the real ingest in Stage 5) on the same video id just replaces the object - no separate "does it already exist" check needed.
- This stage doesn't touch Postgres at all, so it doesn't need `docker compose`'s Postgres service - only MinIO.

## How to run tests properly

```powershell
# 1. Unit tests (pure logic - thumbnail selection, upload call shape - no network needed)
uv run pytest tests/test_thumbnails.py -v

# 2. Full suite (should be all green - 17 tests total after this stage)
uv run pytest

# 3. Lint
uv run ruff check .

# 4. Live end-to-end check (no API key needed - only requires MinIO running)
docker compose up -d
uv run slop ingest inspect-thumbnail dQw4w9WgXcQ
# Then open http://localhost:9001, browse the `thumbnails` bucket, and confirm the image
# renders (it will, regardless of the .jpg/.webp key-vs-content mismatch noted above).

# 5. Try a couple more real video ids of your own choosing to see the more common case
# where the extension does match a real .jpg file.
```
