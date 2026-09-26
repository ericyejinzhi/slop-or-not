# Phase 4, Stage 8 - Thumbnail CLIP embeddings + zero-shot scores

## What is being implemented

`src/sloppy/features/vision.py` - `embed_image` (512-dim CLIP image embedding via HuggingFace `transformers`' `CLIPModel`/`CLIPProcessor`, checkpoint `openai/clip-vit-base-patch32`, per the confirmed decision to reuse `transformers` rather than add `open_clip`) and `zero_shot_scores` (raw cosine similarity against 3 prompts: clickbait, AI-generated, text-heavy). `load_thumbnail_image` reads bytes from MinIO and lets PIL sniff the real format, sidestepping the WebP-under-`.jpg`-key quirk from Phase 1 entirely. Not yet persisted - Stage 9.

Also added: `tests/fixtures/sample_thumbnail.jpg` - a small, self-generated (not downloaded) synthetic test image, so the slow tests don't need a network fetch beyond the one-time CLIP model download.

## A real bug found and fixed while testing against the real model

`CLIPModel.get_image_features()`/`get_text_features()` in this project's installed `transformers` version (5.17.0) return a `BaseModelOutputWithPooling` object, **not** a bare tensor. My first implementation called `.detach().numpy()` directly on that return value, which failed immediately with `AttributeError: 'BaseModelOutputWithPooling' object has no attribute 'detach'` - this is exactly the kind of thing that only shows up when you actually run the real model, not when you write plausible-looking code against remembered API shapes from older tutorials. Diagnosed by loading the real model in a one-off script and inspecting the return object's attributes directly, which revealed `.pooler_output` (a real tensor, shape `(n, 512)`) as the actual embedding. Fixed both `embed_image` and `zero_shot_scores` to read `.pooler_output` before calling `.detach().numpy()`, and updated the fake test doubles to match this real shape rather than the bare-tensor shape I'd originally assumed.

## What it should look like

```python
>>> from PIL import Image
>>> from sloppy.features.vision import embed_image, zero_shot_scores
>>> img = Image.open("tests/fixtures/sample_thumbnail.jpg").convert("RGB")
>>> embed_image(img).shape
(512,)
>>> zero_shot_scores(img)
{'clip_clickbait_score': 0.19, 'clip_ai_generated_score': 0.14, 'clip_text_heavy_score': 0.09}
```

## What to look out for

- **Verified against the real model, twice over.** `embed_image` on the real fixture image returns shape `(512,)` with unit norm (confirmed to within `1e-4`). `zero_shot_scores` returns finite floats in `[-1, 1]` for all 3 prompts against the same real image. Both required the `.pooler_output` fix above to pass at all - before the fix, both slow tests failed immediately with the same `AttributeError`.
- **Zero-shot scores are raw cosine similarities, not softmax-normalized across the prompt set** - a deliberate choice so each prompt's score stays independently meaningful and doesn't shift when a new prompt is added later. Don't expect the 3 scores to sum to 1 or compete against each other.
- `load_thumbnail_image` never inspects the S3 key's extension - `PIL.Image.open` sniffs the real format from the byte stream itself, so the Phase 1 quirk (some thumbnails are WebP bytes stored under a `.jpg`-looking key) is a complete non-issue here, unlike in the labeling CLI's thumbnail cache (Phase 2) which had to derive the extension explicitly.
- The fast test's fake `_FakeOutput`/`_FakeModel` classes exist specifically to mirror the real `BaseModelOutputWithPooling` shape discovered above - if `transformers` changes this API again in a future upgrade, both the fast test's fakes and the real implementation will need updating together (the slow tests would catch a mismatch immediately).

## How to run tests properly

```powershell
uv run pytest tests/test_features_vision.py -v -m "not slow"  # fast, no model
uv run pytest tests/test_features_vision.py -m slow -v          # real CLIP (~600MB download first run)
uv run pytest    # full suite - 109 passed, 5 deselected (all Phase 4 slow tests so far)
uv run ruff check .
```
