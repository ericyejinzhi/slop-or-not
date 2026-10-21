#!/usr/bin/env bash
# One-command AWS deployment. See src/sloppy/deploy_aws.py (or run with --help).
#
#   bash scripts/deploy-aws.sh up --plan-only   show what would be created; change nothing
#   bash scripts/deploy-aws.sh up               create everything and put the app online
#   bash scripts/deploy-aws.sh refresh          push new data, model and code to a running deployment
#   bash scripts/deploy-aws.sh status           is it up?
#   bash scripts/stop-dev.sh --destroy-aws      tear it all down (stops the billing)
#
# Run it from the main checkout with the local stack up (bash scripts/start-dev.sh).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
exec uv run python -m sloppy.deploy_aws "$@"
