from unittest.mock import patch

from sloppy.config import Settings
from sloppy.models.tracking import finish, log_metrics, start_run


def test_start_run_returns_none_when_api_key_unset():
    settings = Settings(_env_file=None, wandb_api_key="")
    run = start_run(settings, config={"foo": "bar"})
    assert run is None


def test_log_metrics_noops_when_run_is_none():
    log_metrics(None, {"metric": 1})  # must not raise


def test_finish_noops_when_run_is_none():
    finish(None)  # must not raise


def test_start_run_never_raises_when_wandb_init_fails():
    # Training must never fail because of W&B - simulate wandb.init() raising (e.g. no
    # network, bad key) via a mock rather than making a real network call in the test
    # suite, and confirm start_run catches it and returns None instead of propagating.
    settings = Settings(_env_file=None, wandb_api_key="fake-key")
    with patch("sloppy.models.tracking.wandb.init", side_effect=RuntimeError("no network")):
        run = start_run(settings, config={"foo": "bar"})
    assert run is None


class _FailingRun:
    def log(self, metrics: dict) -> None:
        raise RuntimeError("network error")


def test_log_metrics_never_raises_when_run_log_fails():
    log_metrics(_FailingRun(), {"metric": 1})  # must not raise
