# ── Uptime monitoring ──
# Route 53 health checkers probe /health/ready from several regions every 30s. The check passes only when the
# response says the background worker is ok, which also implies database and Redis are up (else it returns 503).
# Route 53 publishes health-check metrics only in us-east-1, so the alarm and its email topic live there.

provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = {
      Project     = "provok"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

locals {
  monitor = var.alert_email != "" && var.domain != ""
}

resource "aws_route53_health_check" "site" {
  count             = local.monitor ? 1 : 0
  type              = "HTTPS_STR_MATCH"
  fqdn              = var.domain
  port              = 443
  resource_path     = "/health/ready"
  search_string     = "\"worker\":\"ok\""
  enable_sni        = true
  request_interval  = 30
  failure_threshold = 3
  tags              = { Name = "${local.name}-site" }
}

resource "aws_sns_topic" "alerts" {
  count    = local.monitor ? 1 : 0
  provider = aws.us_east_1
  name     = "${local.name}-alerts"
}

# AWS emails a confirmation link first; alerts arrive only after it is clicked.
resource "aws_sns_topic_subscription" "alerts_email" {
  count     = local.monitor ? 1 : 0
  provider  = aws.us_east_1
  topic_arn = aws_sns_topic.alerts[0].arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_cloudwatch_metric_alarm" "site_down" {
  count               = local.monitor ? 1 : 0
  provider            = aws.us_east_1
  alarm_name          = "${local.name}-site-down"
  alarm_description   = "https://${var.domain}/health/ready failing (site, database, Redis or worker). infra/README.md has the runbook."
  namespace           = "AWS/Route53"
  metric_name         = "HealthCheckStatus"
  dimensions          = { HealthCheckId = aws_route53_health_check.site[0].id }
  statistic           = "Minimum"
  period              = 60
  evaluation_periods  = 2
  comparison_operator = "LessThanThreshold"
  threshold           = 1
  treat_missing_data  = "breaching"
  alarm_actions       = [aws_sns_topic.alerts[0].arn]
  ok_actions          = [aws_sns_topic.alerts[0].arn]
}
