#!/bin/bash
# One-time: create the S3 bucket that holds Terraform state (versioned, encrypted, private).
# Usage: infra/scripts/bootstrap-state.sh [region]
set -euo pipefail
REGION=${1:-ap-south-1}
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
BUCKET="provok-tfstate-$ACCOUNT"
if aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  echo "exists: $BUCKET"
else
  aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" --create-bucket-configuration LocationConstraint="$REGION"
  aws s3api put-bucket-versioning --bucket "$BUCKET" --versioning-configuration Status=Enabled
  aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
  echo "created: $BUCKET"
fi
echo
echo "Now: cd infra/terraform && terraform init -backend-config=\"bucket=$BUCKET\" \\"
echo "  -backend-config=\"key=<environment>/terraform.tfstate\" -backend-config=\"region=$REGION\" -backend-config=\"use_lockfile=true\""
