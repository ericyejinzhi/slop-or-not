"""Trained-model artifacts in object storage (MinIO locally, S3 in production).

A trained model is two files under `<artifacts_dir>/<model_name>/<model_version>/`:
`model.joblib` (the fitted sklearn pipeline) and `metadata.json` (its feature list and
provenance). They are not in git, so a server that did not train the model needs them from
somewhere. `upload_model` publishes them; `ensure_local_model` downloads the active model
on demand when it is not already on disk.

Security note: model.joblib is a pickle, and loading a pickle runs whatever code it
contains. Whoever can write to the models bucket can run code on every server that loads
from it, so the bucket must stay private, with write access limited to the person
publishing models (read-only for the app's instance role).
"""

import logging
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError

from sloppy.config import Settings
from sloppy.storage import ensure_bucket, get_s3_client

logger = logging.getLogger(__name__)

ARTIFACT_FILES = ("model.joblib", "metadata.json")


def _key(model_name: str, model_version: str, filename: str) -> str:
    return f"{model_name}/{model_version}/{filename}"


def local_model_dir(artifacts_dir: Path, model_name: str, model_version: str) -> Path:
    return artifacts_dir / model_name / model_version


def is_local(artifacts_dir: Path, model_name: str, model_version: str) -> bool:
    model_dir = local_model_dir(artifacts_dir, model_name, model_version)
    return all((model_dir / filename).is_file() for filename in ARTIFACT_FILES)


def upload_model(
    client, bucket: str, artifacts_dir: Path, model_name: str, model_version: str
) -> list[str]:
    """Upload a locally trained model's files; creates the bucket if it does not exist.
    Returns the object keys written. Raises FileNotFoundError if the model is not local."""
    model_dir = local_model_dir(artifacts_dir, model_name, model_version)
    missing = [f for f in ARTIFACT_FILES if not (model_dir / f).is_file()]
    if missing:
        raise FileNotFoundError(f"{model_dir} is missing {', '.join(missing)}")

    ensure_bucket(client, bucket)
    keys = []
    for filename in ARTIFACT_FILES:
        key = _key(model_name, model_version, filename)
        client.upload_file(str(model_dir / filename), bucket, key)
        keys.append(key)
    return keys


def download_model(
    client, bucket: str, artifacts_dir: Path, model_name: str, model_version: str
) -> Path:
    """Download a published model into the local artifacts layout and return its directory.
    Each file is written to a temporary name and renamed into place, so a failed or
    interrupted download never leaves a half-written model.joblib that looks complete."""
    model_dir = local_model_dir(artifacts_dir, model_name, model_version)
    model_dir.mkdir(parents=True, exist_ok=True)

    partials = []
    try:
        for filename in ARTIFACT_FILES:
            partial = model_dir / f"{filename}.part"
            client.download_file(bucket, _key(model_name, model_version, filename), str(partial))
            partials.append((partial, model_dir / filename))
    except BaseException:
        for partial, _final in partials:
            partial.unlink(missing_ok=True)
        (model_dir / f"{ARTIFACT_FILES[len(partials)]}.part").unlink(missing_ok=True)
        raise

    for partial, final in partials:
        partial.replace(final)
    return model_dir


def ensure_local_model(
    settings: Settings, artifacts_dir: Path, model_name: str, model_version: str
) -> bool:
    """Make sure the model is on disk, downloading it from the models bucket if needed.
    Returns True only if a download happened. Does nothing (False) when the model is
    already local or when settings.fetch_model_from_s3 is off. A failed download is logged
    and swallowed (False): callers already cope with a missing artifact, and a storage
    hiccup should not turn into a crash of the API or a flow."""
    if is_local(artifacts_dir, model_name, model_version):
        return False
    if not settings.fetch_model_from_s3:
        return False

    try:
        download_model(
            get_s3_client(settings),
            settings.s3_bucket_models,
            artifacts_dir,
            model_name,
            model_version,
        )
    except (BotoCoreError, ClientError, OSError) as exc:
        logger.warning(
            "Could not fetch model %s/%s from s3://%s: %s",
            model_name,
            model_version,
            settings.s3_bucket_models,
            exc,
        )
        return False

    logger.info(
        "Fetched model %s/%s from s3://%s", model_name, model_version, settings.s3_bucket_models
    )
    return True
