# Phase 8, Stage 1 - AWS S3 + RDS config compatibility

## What is being implemented

**Scope note for the whole of Phase 8**: per the decision confirmed with the user, this phase is code/config preparation only - making the codebase genuinely ready to run against real AWS services via env-var changes alone (the "12-factor from day one" principle `ROADMAP.md` states as a design goal back in Phase 0), plus reference infrastructure-as-code. **No real AWS account, credentials, or billable resources are touched anywhere in this phase** - there is no AWS CLI or credentials configured in this environment at all, confirmed before starting.

Two small, additive `Settings` changes (`src/sloppy/config.py`), both backward-compatible with local dev:

- **`s3_endpoint_url` is now `str | None`** (was `str`, always required). MinIO needs an explicit custom endpoint (`http://localhost:9000`); real AWS S3 does not - boto3 resolves the correct regional endpoint itself when no endpoint is given, and forcing an explicit one is the wrong pattern for real S3. A new `aws_region: str = "us-east-1"` setting was added alongside it (previously hardcoded directly in `storage.py::get_s3_client`), since region affects both which endpoint boto3 resolves and how presigned URLs get signed.
- **`postgres_sslmode: str | None = None`** - local Docker Postgres has no TLS configured, so this defaults to not appending anything; RDS in production should set this to `"require"` (or stricter). `database_url`'s property now conditionally appends `?sslmode=...` when set.

`storage.py::get_s3_client` was updated to use `settings.aws_region` instead of the hardcoded `"us-east-1"` literal - the value is now configurable but the default behavior for local dev is unchanged.

A third, related fix: **`s3_access_key`/`s3_secret_key` are now `str | None`**, and `get_s3_client` only passes `aws_access_key_id`/`aws_secret_access_key` to `boto3.client(...)` when both are actually set. Previously they were always passed (even as blank strings), which would silently override boto3's own default credential chain - meaning a real EC2 deployment granting S3 access via an IAM instance role (the secure, no-long-lived-keys-on-disk approach) would never actually get to use that role, since the explicit (blank) credentials would take precedence. Leaving both unset in a production `.env` now correctly lets boto3 fall through to the instance role automatically.

## What it should look like

```python
# Local dev (.env) - unchanged behavior
Settings().s3_endpoint_url  # "http://localhost:9000"
Settings().database_url  # "postgresql+psycopg://slop:...@localhost:5432/slopornot"

# Real AWS (a production .env, prepared but not used anywhere yet)
Settings(s3_endpoint_url=None, aws_region="us-east-1").s3_endpoint_url  # None
# get_s3_client(settings) -> a real boto3 client resolving to
# https://s3.us-east-1.amazonaws.com internally - confirmed by inspecting
# client.meta.endpoint_url directly, not assumed

Settings(postgres_sslmode="require").database_url
# "postgresql+psycopg://...@rds-endpoint:5432/slopornot?sslmode=require"
```

Verified with 7 new tests: `tests/test_config.py` gained `test_database_url_includes_sslmode_when_set`, `test_database_url_omits_sslmode_by_default`, `test_s3_endpoint_url_can_be_unset_for_real_aws_s3` (plus an assertion added to the existing `test_defaults_are_local_dev` confirming `postgres_sslmode` defaults to `None`); a new `tests/test_storage.py` gained 4 tests, all genuinely real checks against real `boto3` client objects, not mocks: `test_get_s3_client_uses_configured_region_and_endpoint`; `test_get_s3_client_resolves_a_real_aws_endpoint_when_endpoint_url_is_none` (constructs a real client, confirms `client.meta.endpoint_url` actually contains `amazonaws.com`); `test_get_s3_client_uses_explicit_credentials_when_both_are_set` and `test_get_s3_client_falls_back_to_default_credential_chain_when_unset` (both inspect `client._request_signer._credentials` directly - confirming explicit credentials resolve when given, and resolve to `None` when withheld, since this sandboxed environment has no ambient AWS credentials of its own to fall back to).

## What to look out for

- **Constructing a boto3 client needs no network access or real AWS credentials at all** - endpoint resolution uses region/service data bundled directly in the SDK, not a live lookup. This is why `test_get_s3_client_resolves_a_real_aws_endpoint_when_endpoint_url_is_none` can genuinely verify real AWS endpoint resolution in a fast, offline unit test, without needing anything from a real account.
- **Neither of the two changes has actually run against a real AWS S3 bucket or RDS instance** - only the local Docker Postgres/MinIO paths and the pure `Settings`/boto3-client-construction logic have been exercised for real. "Does a presigned URL against a real S3 bucket in `us-east-1` actually work end to end" and "does a real RDS connection with `sslmode=require` actually succeed" are both explicitly deferred, same as every "no real data yet" deferral throughout this project - this one is "no real AWS account yet" instead.
- **`s3_bucket_thumbnails` was not made region-aware or account-scoped** - a real S3 bucket name must be globally unique across all of AWS, unlike MinIO's local bucket namespace. This is a real constraint to remember when actually provisioning (it would need a genuinely unique name, e.g. with an account ID or random suffix appended), documented in this phase's Terraform stage rather than solved here in config.
- The purely additive nature of all three changes means every existing test in the project (184 total after this stage) needed zero modifications - confirmed by running the full suite, not assumed.
- `client._request_signer._credentials` is a private boto3 attribute, not a documented public API - there's no cleaner way to introspect resolved credentials without triggering a real network call, so this is a pragmatic, slightly fragile-to-a-future-boto3-upgrade check, flagged as such rather than presented as a stable public interface.

## How to run tests properly

```powershell
uv run pytest tests/test_config.py tests/test_storage.py -v
uv run pytest    # full suite - 184 passed, 5 deselected
uv run ruff check .
uv run ruff format --check .
```

All 10 tests in these two files are pure/fast - no Docker, no network, no real AWS credentials needed for any of them.
