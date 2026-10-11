#!/bin/bash
# Run Terraform against one environment, so staging and production can never share (or overwrite) a state file.
# Usage: infra/scripts/tf.sh <staging|production> plan|apply|output ... [extra terraform args]
#   infra/scripts/tf.sh production plan          (writes production.tfplan; apply it with:)
#   infra/scripts/tf.sh production apply production.tfplan
# Per-environment variables live in infra/terraform/<environment>.tfvars (gitignored; see infra/README.md).
set -euo pipefail
export MSYS_NO_PATHCONV=1
ENVIRONMENT=${1:?environment (staging|production)} CMD=${2:?terraform command}
shift 2
case $ENVIRONMENT in staging|production) ;; *) echo "unknown environment: $ENVIRONMENT" >&2; exit 1 ;; esac
cd "$(dirname "$0")/../terraform"
VARS="$ENVIRONMENT.tfvars"
[ -f "$VARS" ] || { echo "missing infra/terraform/$VARS (see infra/README.md)" >&2; exit 1; }

ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
terraform init -input=false -reconfigure \
  -backend-config="bucket=provok-tfstate-$ACCOUNT" -backend-config="key=$ENVIRONMENT/terraform.tfstate" \
  -backend-config="region=ap-south-1" -backend-config="use_lockfile=true" > /dev/null

case $CMD in
  plan)  terraform plan -input=false -var-file="$VARS" -var="environment=$ENVIRONMENT" -out="$ENVIRONMENT.tfplan" "$@" ;;
  apply) terraform apply -input=false "${@:-$ENVIRONMENT.tfplan}" ;;
  *)     terraform "$CMD" "$@" ;;
esac
