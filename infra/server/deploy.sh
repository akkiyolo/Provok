#!/bin/bash
# Runs ON the server (via SSM, as root): bring the stack to the images tagged <tag>.
# Usage: deploy.sh <environment> <tag> <deploy-bucket> <region>
set -euo pipefail
ENVIRONMENT=$1 TAG=$2 BUCKET=$3 REGION=$4
cd /opt/provok

aws s3 cp "s3://$BUCKET/$TAG/docker-compose.yml" docker-compose.yml --region "$REGION" --only-show-errors
OLD_CADDYFILE=$(sha256sum Caddyfile 2>/dev/null || true)
aws s3 cp "s3://$BUCKET/$TAG/Caddyfile" Caddyfile --region "$REGION" --only-show-errors

# Secrets live in SSM Parameter Store, never on GitHub or in the image.
umask 077
aws ssm get-parameter --name "/provok/$ENVIRONMENT/env" --with-decryption --region "$REGION" \
  --query Parameter.Value --output text > .env.new
mv .env.new .env

ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGISTRY="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY"
# Recorded in .env too, so later manual `docker compose logs/exec` on the server resolve the same images.
printf 'API_IMAGE=%s\nWEB_IMAGE=%s\n' "$REGISTRY/provok-$ENVIRONMENT/api:$TAG" "$REGISTRY/provok-$ENVIRONMENT/web:$TAG" >> .env
# Error reports from the API and worker carry the deployed version (the web bundle gets the same tag at build).
printf 'RELEASE=%s\n' "$TAG" >> .env

docker compose pull --quiet
docker compose up -d --wait redis
if grep -q '^COMPOSE_PROFILES=.*localdb' .env; then docker compose up -d --wait postgres; fi
docker compose run --rm --no-deps api python -m backend.app.cli migrate
docker compose up -d --remove-orphans --wait
# Caddy reads its config only at start, and the bind mount may still point at the replaced file.
if [ "$(sha256sum Caddyfile)" != "$OLD_CADDYFILE" ]; then docker compose up -d --force-recreate --no-deps caddy; fi
docker image prune -af --filter "until=168h" > /dev/null
echo "deployed $TAG"
