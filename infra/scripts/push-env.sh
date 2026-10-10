#!/bin/bash
# Store a server .env in SSM Parameter Store (SecureString). The server reads it on every deploy.
# Usage: infra/scripts/push-env.sh <environment> <env-file> [region]
# Comments and blank lines are stripped. Never commit the env file (.env.* is gitignored).
set -euo pipefail
ENVIRONMENT=$1 FILE=$2 REGION=${3:-ap-south-1}
BODY=$(grep -vE '^\s*(#|$)' "$FILE")
# Values reach the app literally (compose env_file format: raw), so an inline "# note" would become part of the value.
if grep -nE '^[A-Za-z_][A-Za-z0-9_]*=.*[[:space:]]#' <<<"$BODY"; then
  echo "error: inline comments above; move them to their own line" >&2; exit 1
fi
TIER=Standard
[ "${#BODY}" -gt 4000 ] && TIER=Advanced # Standard parameters max out at 4 KB
aws ssm put-parameter --name "/provok/$ENVIRONMENT/env" --type SecureString --tier "$TIER" --overwrite \
  --region "$REGION" --value "$BODY" --query Version --output text | sed "s/^/stored \/provok\/$ENVIRONMENT\/env version /"
echo "Takes effect on the next deploy (GitHub: Actions → Deploy → Run workflow)."
