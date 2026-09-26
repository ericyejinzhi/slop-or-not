# Phase 2, Stage 5 - Interactive labeling CLI

## What is being implemented

The actual labeling tool: `slop label run` shows each video's title/channel/stats, auto-opens its thumbnail, reads a single keystroke, and records a judgment - the roadmap's "keyboard-driven labeling CLI."

- `src/sloppy/label/keyboard.py` - `read_key()` (thin wrapper over `readchar.readkey()`) and a pure `action_for_key()` mapping: **`y`=up, `n`=down, `s`=skip, `q`=quit**.
- `src/sloppy/label/display.py` - `cache_thumbnail()` downloads a video's thumbnail from MinIO to a unique per-video local file (reading the real `s3_bucket`/`s3_key`/`content_type` off the video's `thumbnails` row, not re-derived/assumed) and `open_image()` auto-opens it (`os.startfile`).
- `src/sloppy/label/labels.py` - `record_label()`, a plain insert into `labels`.
- `slop label run` - ties it together: resolve pool -> per video, print info + open thumbnail + read a key + record the label + commit -> stop after `--limit` or when the pool runs out.
- New dependency: `readchar` (your call, over stdlib `msvcrt`, for cross-platform portability).

## A real bug found and fixed during this stage

The plan's `cache_thumbnail` was supposed to derive the cache file's extension from the thumbnail's actual `content_type`, specifically *because* Phase 1 found some thumbnails are WebP bytes under a `.jpg` S3 key. My first implementation used Python's stdlib `mimetypes.guess_extension()` for this - and on this machine, `mimetypes.guess_extension("image/webp")` returns `None` (WebP isn't universally registered in the OS/stdlib mimetypes database), which silently fell back to `.jpg` and **exactly reproduced the bug this code was supposed to prevent**. Fixed by hardcoding an explicit `content_type -> extension` map for the handful of formats YouTube thumbnails actually come back as (`image/jpeg`, `image/webp`, `image/png`, `image/gif`), falling back to `mimetypes.guess_extension()` and then `.jpg` only for anything unexpected. Added a regression test (`test_extension_for_content_type_does_not_silently_fall_back_to_jpg_for_webp`) that would have caught this.

## What it should look like

```
$ uv run slop label run --limit 5
Labeling as 'eric'. 400 video(s) in this pool.
Keys: y=up (quality)   n=down (slop)   s=skip   q=quit

'Some Video Title'
  channel:   @somechannel
  published: 2026-08-01 12:00:00+00:00
  duration:  612s
  views/likes/comments: 12345/987/65
  [y]up  [n]down  [s]kip  [q]uit > y

'Another Video'
  ...
```

(the thumbnail pops open in your default image viewer as each video is shown)

## What to look out for

- **The interactive keypress loop itself cannot be tested headlessly, and I confirmed why rather than just assuming it.** I tried piping `"q"` into `slop label run` from this environment to test the quit path automatically - it hung. `readchar` reads directly from the console device (similar to `msvcrt.getch()` under the hood on Windows), not from redirected/piped stdin, so there's no way to drive it from a non-interactive script. Everything **up to** the keypress was confirmed working from that same run (pool selection, video info printing, the "no thumbnail on record" warning path) before I had to stop the hung process. **You'll need to run `slop label run` yourself in a real terminal to test the actual keystrokes** - that's not a gap I could have closed automatically.
- What I *could* verify end-to-end against real Postgres + MinIO (via a direct script, not the interactive CLI): inserted a synthetic video with a real uploaded thumbnail, confirmed `candidate_videos` found it, `cache_thumbnail` downloaded the exact bytes back from MinIO, and after `record_label` ran, the same video no longer appeared in a fresh pool query. All cleaned up afterward.
- If a video has no `thumbnails` row at all (shouldn't happen for anything ingested via Phase 1's normal pipeline, but could happen with hand-inserted test data or a video whose thumbnail step failed during ingestion), the CLI prints a `[warn] no thumbnail on record` line and continues rather than crashing.
- Labels commit one at a time (`session_scope()` per video), matching Phase 1's "commit per item" philosophy - closing the terminal mid-session loses at most whatever video was on screen, not the whole session.
- `--labeler` overrides `.env`'s `LABELER_NAME` for a single run; if neither is set, the command refuses to start rather than silently recording blank-labeler rows.

## How to run tests properly

```powershell
# 1. Full suite - includes keyboard-mapping unit tests and thumbnail-caching tests
#    (using a fake S3 client + monkeypatched cache dir, no real network/MinIO needed
#    for these particular tests)
uv run pytest tests/test_label_keyboard.py tests/test_label_display.py tests/test_label_labels.py -v
uv run pytest

# 2. Lint
uv run ruff check .

# 3. The real test - run it yourself, in a real terminal, once you have some ingested
#    videos and LABELER_NAME set in .env:
uv run slop label run --limit 5
# label a handful with each key (y, n, s), then confirm:
docker compose exec postgres psql -U slop -d slopornot -c "select label, count(*) from labels group by 1;"
# re-run the same command and confirm those 5 videos do not reappear
```
