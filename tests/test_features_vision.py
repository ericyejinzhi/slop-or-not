from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from sloppy.features import vision
from sloppy.features.vision import CLIP_ZERO_SHOT_PROMPTS, embed_image, zero_shot_scores

FIXTURE_IMAGE = Path(__file__).parent / "fixtures" / "sample_thumbnail.jpg"


class _FakeTensor:
    def __init__(self, array: np.ndarray):
        self._array = array

    def detach(self):
        return self

    def numpy(self):
        return self._array


class _FakeOutput:
    """Mimics transformers' BaseModelOutputWithPooling shape - the real
    get_image_features/get_text_features return this, not a bare tensor."""

    def __init__(self, array: np.ndarray):
        self.pooler_output = _FakeTensor(array)


class _FakeModel:
    def get_image_features(self, **kwargs):
        return _FakeOutput(np.array([[1.0, 0.0, 0.0]]))

    def get_text_features(self, **kwargs):
        # order matches CLIP_ZERO_SHOT_PROMPTS' 3 keys: clickbait, ai_generated, text_heavy
        return _FakeOutput(np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]))


class _FakeProcessor:
    def __call__(self, images=None, text=None, return_tensors=None, padding=None):
        return {}


def test_zero_shot_scores_dict_shape_and_keys(monkeypatch):
    monkeypatch.setattr(vision, "_load_clip", lambda: (_FakeModel(), _FakeProcessor()))

    tiny_image = Image.new("RGB", (2, 2))
    scores = zero_shot_scores(tiny_image)

    assert set(scores.keys()) == set(CLIP_ZERO_SHOT_PROMPTS.keys())
    # image_vec == [1,0,0] (already unit norm); text vecs are the 3 orthogonal axes in
    # the same key order, so the dot products are exact: 1.0, 0.0, 0.0
    assert scores["clip_clickbait_score"] == pytest.approx(1.0)
    assert scores["clip_ai_generated_score"] == pytest.approx(0.0, abs=1e-9)
    assert scores["clip_text_heavy_score"] == pytest.approx(0.0, abs=1e-9)


@pytest.mark.slow
def test_embed_image_real_model_unit_norm():
    image = Image.open(FIXTURE_IMAGE).convert("RGB")
    vec = embed_image(image)
    assert vec.shape == (512,)
    assert abs(np.linalg.norm(vec) - 1.0) < 1e-4


@pytest.mark.slow
def test_zero_shot_scores_real_model_produces_finite_sane_scores():
    image = Image.open(FIXTURE_IMAGE).convert("RGB")
    scores = zero_shot_scores(image)
    assert set(scores.keys()) == set(CLIP_ZERO_SHOT_PROMPTS.keys())
    for value in scores.values():
        assert np.isfinite(value)
        assert -1.0 <= value <= 1.0
