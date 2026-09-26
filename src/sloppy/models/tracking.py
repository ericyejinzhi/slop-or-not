"""Best-effort Weights & Biases run tracking. Training must never fail because of W&B -
every function here no-ops (returns None / does nothing) if wandb_api_key is unset, or if
wandb itself raises for any reason (no network, bad key, etc).
"""

import logging

import wandb

from sloppy.config import Settings

logger = logging.getLogger(__name__)


def start_run(settings: Settings, config: dict) -> wandb.sdk.wandb_run.Run | None:
    if not settings.wandb_api_key:
        logger.info("WANDB_API_KEY not set - skipping W&B tracking for this run")
        return None
    try:
        return wandb.init(project=settings.wandb_project, config=config)
    except Exception as exc:  # noqa: BLE001 - tracking is best-effort, never fatal
        logger.warning("W&B run failed to start (%s) - continuing without tracking", exc)
        return None


def log_metrics(run: wandb.sdk.wandb_run.Run | None, metrics: dict) -> None:
    if run is None:
        return
    try:
        run.log(metrics)
    except Exception as exc:  # noqa: BLE001
        logger.warning("W&B log_metrics failed (%s) - continuing without tracking", exc)


def finish(run: wandb.sdk.wandb_run.Run | None) -> None:
    if run is None:
        return
    try:
        run.finish()
    except Exception as exc:  # noqa: BLE001
        logger.warning("W&B finish failed (%s)", exc)
