output "site_url" {
  value = "https://${local.site_domain}"
}

output "public_ip" {
  value = aws_eip.app.public_ip
}

output "instance_id" {
  description = "Open a shell: aws ssm start-session --target <id>"
  value       = aws_instance.app.id
}

output "deploy_role_arn" {
  description = "Set as the GitHub repository variable AWS_DEPLOY_ROLE_ARN."
  value       = aws_iam_role.deploy.arn
}

output "env_parameter" {
  description = "SecureString holding the server's .env (write it with infra/scripts/push-env.sh)."
  value       = local.env_param
}

output "media_bucket" {
  value = aws_s3_bucket.media.bucket
}

output "media_base_url" {
  value = "https://${aws_s3_bucket.media.bucket_regional_domain_name}"
}

output "ses_dkim_records" {
  description = "Add these CNAMEs at your DNS provider to verify the SES domain (created automatically when dns_zone covers it)."
  value = var.ses_domain == "" ? [] : [
    for t in aws_sesv2_email_identity.domain[0].dkim_signing_attributes[0].tokens :
    { name = "${t}._domainkey.${var.ses_domain}", type = "CNAME", value = "${t}.dkim.amazonses.com" }
  ]
}

output "dns_nameservers" {
  description = "Set these as the domain's nameservers at the registrar (only when this stack created the zone)."
  value       = var.dns_zone != "" && var.create_dns_zone ? aws_route53_zone.main[0].name_servers : []
}

output "database_url" {
  description = "DATABASE_URL for the server .env when database = \"rds\" (terraform output -raw database_url)."
  value       = local.rds ? "postgresql://provok:${random_password.db[0].result}@${aws_db_instance.main[0].endpoint}/provok?sslmode=require" : ""
  sensitive   = true
}
