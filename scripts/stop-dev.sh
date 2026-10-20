#!/usr/bin/env bash
# Stops everything the local dev workflow starts: the FastAPI backend (uvicorn, including
# its --reload watcher process), the Vite frontend dev server, and the docker compose
# services (postgres, minio). Safe to re-run - each step is a no-op if already stopped.
#
# It then prints a read-only report of anything in AWS that is still costing money, so you
# know before you walk away. The report never changes anything.
#
# Usage: bash scripts/stop-dev.sh                 stop local services + AWS billing report
#        bash scripts/stop-dev.sh --destroy-aws   also `terraform destroy` the deployment
#        bash scripts/stop-dev.sh --destroy-aws --yes   ...without the typed confirmation
#
# --destroy-aws deletes the server, the database (NO final snapshot) and both S3 buckets
# including their contents. Everything can be rebuilt from your local data by following
# docs/deploy-runbook.md, but only by redoing its data steps.
set -uo pipefail

DESTROY_AWS=0
ASSUME_YES=0
for arg in "$@"; do
  case "$arg" in
    --destroy-aws) DESTROY_AWS=1 ;;
    --yes) ASSUME_YES=1 ;;
    *) echo "Unknown option: $arg (use --destroy-aws [--yes])"; exit 2 ;;
  esac
done

stop_port() {
  local port="$1" label="$2"
  local pid
  pid=$(powershell.exe -NoProfile -Command \
    "(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess)" \
    2>/dev/null | tr -d '\r\n')
  if [ -z "$pid" ]; then
    echo "  $label: not running (port $port free)"
    return
  fi

  # uvicorn --reload runs a watcher (parent) process plus a server (child) process -
  # whichever one actually holds the port, kill both so neither is left orphaned.
  local parent
  parent=$(powershell.exe -NoProfile -Command \
    "(Get-CimInstance Win32_Process -Filter \"ProcessId=$pid\").ParentProcessId" \
    2>/dev/null | tr -d '\r\n')

  echo "  $label: stopping pid $pid (port $port)${parent:+, parent $parent}"
  taskkill //PID "$pid" //T //F > /dev/null 2>&1
  [ -n "$parent" ] && taskkill //PID "$parent" //T //F > /dev/null 2>&1
}

echo "Stopping dev services..."
stop_port 8000 "API (uvicorn)"
# Vite starts at 5173 and bumps up if taken - stop whichever one actually ended up running.
for port in 5173 5174 5175 5176 5177 5178; do
  stop_port "$port" "frontend (vite, port $port)"
done

echo "Stopping docker compose services (postgres, minio, ...)..."
cd "$(dirname "${BASH_SOURCE[0]}")/.."
ROOT="$PWD"
docker compose stop

# Read-only: list the AWS resources that bill while they exist. Prints the number of
# billable things found so the caller can tell "clean" from "still paying".
AWS_REGION_TO_CHECK="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-2}}"
aws_billing_report() {
  BILLABLE=0
  if ! command -v aws > /dev/null 2>&1; then
    echo "  aws CLI not found - cannot check AWS. Check the console yourself."
    return
  fi
  if ! aws sts get-caller-identity > /dev/null 2>&1; then
    echo "  AWS credentials not working - cannot check AWS (run: aws configure)."
    return
  fi
  local r="$AWS_REGION_TO_CHECK" out
  export AWS_PAGER=""
  out=$(aws ec2 describe-instances --region "$r" --filters Name=instance-state-name,Values=pending,running,stopping,stopped     --query 'Reservations[].Instances[].[InstanceId,State.Name,InstanceType]' --output text 2>&1)
  echo "  EC2 instances:   ${out:-none}"; [ -n "$out" ] && BILLABLE=$((BILLABLE + 1))
  out=$(aws rds describe-db-instances --region "$r"     --query 'DBInstances[].[DBInstanceIdentifier,DBInstanceStatus,DBInstanceClass]' --output text 2>&1)
  echo "  RDS databases:   ${out:-none}"; [ -n "$out" ] && BILLABLE=$((BILLABLE + 1))
  out=$(aws ec2 describe-volumes --region "$r"     --query 'Volumes[].[VolumeId,State,Size]' --output text 2>&1)
  echo "  EBS disks (GB):  ${out:-none}"; [ -n "$out" ] && BILLABLE=$((BILLABLE + 1))
  out=$(aws ec2 describe-addresses --region "$r" --query 'Addresses[].PublicIp' --output text 2>&1)
  echo "  Elastic IPs:     ${out:-none}"; [ -n "$out" ] && BILLABLE=$((BILLABLE + 1))
  out=$(aws ec2 describe-nat-gateways --region "$r" --filter Name=state,Values=pending,available     --query 'NatGateways[].NatGatewayId' --output text 2>&1)
  echo "  NAT gateways:    ${out:-none}"; [ -n "$out" ] && BILLABLE=$((BILLABLE + 1))
  out=$(aws s3 ls 2>&1)
  echo "  S3 buckets:      ${out:-none}  (pennies a month; not counted below)"
  if [ "$BILLABLE" -eq 0 ]; then
    echo "  => nothing that bills by the hour is left in $r."
  else
    echo "  => $BILLABLE kind(s) of resource still billing in $r (about \$1-2 a day for this project)."
  fi
}

destroy_aws() {
  local tfdir="$ROOT/infra/terraform"
  if ! command -v terraform > /dev/null 2>&1; then
    echo "  terraform not found on PATH - cannot destroy. Open a fresh terminal if you just installed it."
    return 1
  fi
  if [ ! -f "$tfdir/terraform.tfstate" ]; then
    echo "  No $tfdir/terraform.tfstate here (run this from the main checkout, not a worktree)."
    echo "  Without that state file Terraform would not know what to destroy. Skipping."
    return 1
  fi
  echo "  This DELETES the server, the database (no final snapshot) and both S3 buckets with their contents."
  if [ "$ASSUME_YES" -ne 1 ]; then
    local answer
    read -r -p "  Type 'destroy' to continue: " answer
    if [ "$answer" != "destroy" ]; then
      echo "  Not confirmed - nothing destroyed."
      return 1
    fi
  fi
  # Destroying never reads the database password, but Terraform insists the variable has a value.
  export TF_VAR_db_password="${TF_VAR_db_password:-destroy-placeholder-not-used}"
  (cd "$tfdir" && terraform destroy -auto-approve -input=false)
}

echo "AWS billing check (region $AWS_REGION_TO_CHECK, read-only):"
aws_billing_report

if [ "$DESTROY_AWS" -eq 1 ]; then
  echo "Destroying the AWS deployment..."
  if destroy_aws; then
    echo "AWS billing check after destroy:"
    aws_billing_report
  fi
elif [ "${BILLABLE:-0}" -gt 0 ]; then
  echo "  To stop that billing: bash scripts/stop-dev.sh --destroy-aws"
fi

echo "Done."
