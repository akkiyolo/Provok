#!/bin/bash
# Save credits: stop the staging server when nobody is testing. Data (Postgres volume) is kept.
# Usage: infra/scripts/staging.sh start|stop|status|shell [environment] [region]
set -euo pipefail
export MSYS_NO_PATHCONV=1 # Git Bash on Windows would rewrite "/provok/..." into a Windows path
ACTION=${1:?start|stop|status|shell} ENVIRONMENT=${2:-staging} REGION=${3:-ap-south-1}
ID=$(aws ec2 describe-instances --region "$REGION" \
  --filters "Name=tag:Name,Values=provok-$ENVIRONMENT-app" "Name=instance-state-name,Values=pending,running,stopping,stopped" \
  --query 'Reservations[0].Instances[0].InstanceId' --output text)
[ "$ID" = "None" ] && { echo "no provok-$ENVIRONMENT server found"; exit 1; }
ALARM="provok-$ENVIRONMENT-site-down"
case $ACTION in
  start)  aws ec2 start-instances --region "$REGION" --instance-ids "$ID" > /dev/null
          aws ec2 wait instance-running --region "$REGION" --instance-ids "$ID"; echo "running ($ID); the site is back in ~1 min"
          # Uptime alerts were paused by `stop`; resume them once the site has had time to come up.
          nohup sh -c "sleep 300; aws cloudwatch enable-alarm-actions --region us-east-1 --alarm-names $ALARM" >/dev/null 2>&1 &
          echo "uptime alerts resume in 5 min" ;;
  stop)   aws cloudwatch disable-alarm-actions --region us-east-1 --alarm-names "$ALARM" 2>/dev/null || true
          aws ec2 stop-instances --region "$REGION" --instance-ids "$ID" > /dev/null; echo "stopping ($ID); uptime alerts paused" ;;
  status) aws ec2 describe-instances --region "$REGION" --instance-ids "$ID" --query 'Reservations[0].Instances[0].State.Name' --output text ;;
  shell)  aws ssm start-session --region "$REGION" --target "$ID" ;;
  *)      echo "unknown action: $ACTION"; exit 1 ;;
esac
