# Predicting from a pasted link

## What is being implemented
A visitor pastes a YouTube link and gets a slop score for that one video, without anything being added to the dataset. Predicting is the general use of the tool; changing the dataset (ingesting, labeling, retraining) stays an admin action done locally.

## How it works
1. `POST /predict {"url": ...}` parses the link (`predict/url.py`: watch, youtu.be, Shorts, embed and live links, or a bare 11-character id; anything else is refused).
2. It reads the video's metadata, its top 100 comments, the channel's name and the thumbnail from YouTube, all in memory.
3. It builds the same features training used, with the same functions (`predict/service.py`). The text features come from `features/pipeline.py:nlp_feature_values`, which was pulled out of the batch pipeline so training and prediction cannot drift apart.
4. It scores with the **video-only model** (`VIDEO_ONLY_MODEL_NAME` / `VIDEO_ONLY_MODEL_VERSION`), the one trained without the six features that compare a video with the rest of its channel (see `docs/writeups/phase-3/cross-validation.md`, update 2026-10-20). A link gives no channel history to compute those from.
5. It explains the score (`predict/explain.py`): per-feature contributions in log-odds, one-hot columns folded back into their feature, shown on the page as "points toward / away from slop".
6. It adds read-only context: the stored videos with the nearest thumbnails, and whether the channel is already in the dataset (with its average score when it is).

## What it does not do
It writes nothing: no rows in any table, no files in object storage, no labels. The only database access is read-only (genre length norms, thumbnail neighbours, the channel lookup). `tests/test_predict_service.py` asserts the row counts of every table are unchanged after a prediction, and fails if the code touches S3.

## Safe to leave open on a read-only server
`POST /predict` is the one POST a read-only deployment still serves (`READ_ONLY_POST_PATHS` in `api/app.py`); every other write stays blocked, including paths added later. Because anyone who can reach the site can call it, and each call spends YouTube API quota and CPU:
- it is rate limited per client (`PREDICT_RATE_LIMIT_PER_HOUR`, default 20, 0 = off), with `Retry-After` on the refusal;
- it runs one at a time (a second request waits up to 90 seconds, then gets a "busy" answer);
- the client address is read from `X-Real-IP` only when `TRUST_PROXY_HEADERS` is on, which is correct only while the API is reachable solely through the nginx container (true on the AWS setup, where only port 80 is open). A forged header otherwise buys a fresh allowance.
The limiter is in memory, so it resets on restart and is a cost guard, not a security boundary.

## Settings
| Setting | Meaning |
|---|---|
| `VIDEO_ONLY_MODEL_NAME`, `VIDEO_ONLY_MODEL_VERSION` | the model used (required for predictions) |
| `YOUTUBE_API_KEY` | needed to read the video (required) |
| `PREDICT_RATE_LIMIT_PER_HOUR` | per-client limit, default 20 |
| `TRUST_PROXY_HEADERS` | read the client address from `X-Real-IP` (behind nginx only) |

`GET /config` reports `predict_enabled`, true only when the model and the key are both set; the dashboard shows the "Check a video" page only then.

## Running it
Locally: `bash scripts/start-dev.sh`, open the dashboard, and choose "Check a video". From the command line there is no separate command; the API is the interface.

## What to look out for
- **Accuracy is modest and uneven.** A single video is a weaker signal than a channel average (in cross-validation the video-only XGBoost scored ROC-AUC 0.83 per video against 0.89 for channel averages). The page says so. The explanation shows what the model used, not what is true: it can lean on quirks of the 105 labeled channels.
- **The first prediction after the server starts is the slowest** (the language, embedding and image models load into memory); later ones are quicker.
- **Very short videos are scored mostly on their length.** In the 1,072 stored videos, 401 are 3 minutes or less and most of those are labeled slop, so the model learned that short plus no genre reads as slop. A 19-second video from 2005 ("Me at the zoo") scored 0.82 for exactly that reason, driven by length and a missing genre. It is a limit of the training data, not a bug, and the page's caveat applies most strongly to Shorts and other very short videos.
- **Measured cost (a laptop with a hybrid CPU, 100 comments):** about 13 seconds warm and 20-27 seconds on the first call; text features are the bulk (9-13 s), then the thumbnail download (2-3 s) and CLIP (0.4-3 s). The api process peaked near 1.7 GB resident with all models loaded, which is why the server default is a 4 GB `t3.medium`. A server CPU may be slower; nginx allows 180 seconds.
- **A channel's other videos are not used.** Anything that depends on them is deliberately absent from this model.
- **Videos with comments off, or no thumbnail, still get a score** with those signals left out and a warning on the page.
