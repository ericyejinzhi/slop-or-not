"""Tests sloppy.storage.get_s3_client's region/endpoint configuration - constructing a
boto3 client needs no network access or real credentials (endpoint resolution uses data
bundled with the SDK), so this is fast and fully offline.
"""

from sloppy.config import Settings
from sloppy.storage import get_s3_client


def test_get_s3_client_uses_configured_region_and_endpoint():
    settings = Settings(_env_file=None, aws_region="eu-west-1")
    client = get_s3_client(settings)
    assert client.meta.region_name == "eu-west-1"
    assert client.meta.endpoint_url == settings.s3_endpoint_url


def test_get_s3_client_resolves_a_real_aws_endpoint_when_endpoint_url_is_none():
    """Phase 8: real AWS S3 deployments leave s3_endpoint_url unset so boto3 resolves
    the correct regional endpoint itself, rather than hardcoding one."""
    settings = Settings(_env_file=None, s3_endpoint_url=None, aws_region="us-west-2")
    client = get_s3_client(settings)
    assert client.meta.region_name == "us-west-2"
    assert client.meta.endpoint_url is not None
    assert "amazonaws.com" in client.meta.endpoint_url


def test_get_s3_client_uses_explicit_credentials_when_both_are_set():
    settings = Settings(_env_file=None, s3_access_key="key", s3_secret_key="secret")
    client = get_s3_client(settings)
    credentials = client._request_signer._credentials
    assert credentials.access_key == "key"
    assert credentials.secret_key == "secret"


def test_get_s3_client_falls_back_to_default_credential_chain_when_unset():
    """Phase 8: an EC2 deployment leaving these unset should let boto3 pick up an
    instance IAM role instead - confirmed here by checking no explicit credentials were
    resolved (this sandboxed test environment has no ambient AWS credentials of its own
    - no ~/.aws, no AWS_* env vars - confirmed directly before writing this test)."""
    settings = Settings(_env_file=None, s3_access_key=None, s3_secret_key=None)
    client = get_s3_client(settings)
    assert client._request_signer._credentials is None
