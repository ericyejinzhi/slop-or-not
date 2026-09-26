"""Thumbnail CLIP embeddings + zero-shot scores, via HuggingFace transformers
(CLIPModel/CLIPProcessor) - not open_clip, per the confirmed decision to reuse the
dependency already needed for sentiment rather than add a second CLIP library.
"""

import io
from functools import lru_cache

import numpy as np
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

CLIP_MODEL_NAME = "openai/clip-vit-base-patch32"
CLIP_EMBEDDING_DIM = 512

CLIP_ZERO_SHOT_PROMPTS = {
    "clip_clickbait_score": "a clickbait thumbnail with exaggerated expressions",
    "clip_ai_generated_score": "an AI-generated image",
    "clip_text_heavy_score": "a thumbnail with large bold text overlay",
}


@lru_cache
def _load_clip() -> tuple[CLIPModel, CLIPProcessor]:
    model = CLIPModel.from_pretrained(CLIP_MODEL_NAME)
    processor = CLIPProcessor.from_pretrained(CLIP_MODEL_NAME)
    return model, processor


def load_thumbnail_image(s3_client, bucket: str, key: str) -> Image.Image:
    """PIL sniffs the actual image format from bytes, not the key's extension - the
    WebP-under-.jpg-key quirk noted for Thumbnail in Phase 1 is a non-issue here."""
    data = s3_client.get_object(Bucket=bucket, Key=key)["Body"].read()
    return Image.open(io.BytesIO(data)).convert("RGB")


def _normalize(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    if norm == 0:
        return vec
    return vec / norm


def embed_image(image: Image.Image) -> np.ndarray:
    model, processor = _load_clip()
    inputs = processor(images=image, return_tensors="pt")
    # get_image_features returns a BaseModelOutputWithPooling in this transformers
    # version, not a bare tensor - the actual embedding is .pooler_output.
    output = model.get_image_features(**inputs)
    return _normalize(output.pooler_output.detach().numpy()[0])


def zero_shot_scores(image: Image.Image) -> dict[str, float]:
    """Raw cosine similarities, NOT softmax-normalized across the prompt set - keeps
    each score independently meaningful and stable as prompts are added later (softmax
    would shift every existing score whenever a new prompt joins)."""
    model, processor = _load_clip()
    image_vec = embed_image(image)

    prompt_names = list(CLIP_ZERO_SHOT_PROMPTS.keys())
    prompt_texts = list(CLIP_ZERO_SHOT_PROMPTS.values())
    text_inputs = processor(text=prompt_texts, return_tensors="pt", padding=True)
    text_features = model.get_text_features(**text_inputs).pooler_output.detach().numpy()

    scores = {}
    for name, text_vec in zip(prompt_names, text_features, strict=True):
        scores[name] = float(np.dot(image_vec, _normalize(text_vec)))
    return scores
