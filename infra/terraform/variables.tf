variable "environment" {
  description = "Environment name; also namespaces every resource (provok-<environment>-...)."
  type        = string
  default     = "staging"
}

variable "region" {
  description = "AWS region. Mumbai keeps latency low for users in India."
  type        = string
  default     = "ap-south-1"
}

variable "instance_type" {
  description = "One small x86 server runs Caddy, web, API (+ embedded worker), Redis and (staging) Postgres."
  type        = string
  default     = "t3.small"
}

variable "root_volume_gb" {
  description = "Root EBS volume size (Docker images, Postgres data on staging, swap)."
  type        = number
  default     = 30
}

variable "domain" {
  description = "Public hostname for the site. Empty = <elastic-ip-with-dashes>.sslip.io, which works with HTTPS before a domain is bought."
  type        = string
  default     = ""
}

variable "dns_zone" {
  description = "Domain whose DNS Route 53 hosts (e.g. provok.in). Empty = no DNS management."
  type        = string
  default     = ""
}

variable "create_dns_zone" {
  description = "The Route 53 zone is one per account: create it in the first stack, look it up in later ones."
  type        = bool
  default     = true
}

variable "alert_email" {
  description = "Where uptime alerts go (needs `domain`). AWS emails a confirmation link first. Empty = no monitoring."
  type        = string
  default     = ""
}

variable "ses_domain" {
  description = "Domain to send email from via SES (creates the identity and DKIM records to add to DNS). Empty = skip."
  type        = string
  default     = ""
}

variable "ses_sender_emails" {
  description = "Individual addresses to verify in SES (each gets a confirmation email). Useful before a domain exists, and for sandbox testing."
  type        = list(string)
  default     = []
}

variable "github_repository" {
  description = "owner/name of the GitHub repo allowed to deploy via OIDC."
  type        = string
  default     = "akkiyolo/Provok"
}

variable "github_repository_ids" {
  description = "Numeric \"<owner id>/<repo id>\" of github_repository. GitHub now puts them in the OIDC subject (repo:owner@id/name@id:...); they never change, unlike names. Shown in CloudTrail on a denied AssumeRoleWithWebIdentity."
  type        = string
  default     = "188705432/1349665845"
}

variable "deploy_branch" {
  description = "Only workflows running on this branch may assume the deploy role."
  type        = string
  default     = "main"
}

variable "create_github_oidc_provider" {
  description = "The GitHub OIDC provider is one per AWS account: create it in the first stack, reuse it in later ones."
  type        = bool
  default     = true
}

variable "compose_version" {
  description = "Docker Compose plugin release installed on the server (checksum-verified)."
  type        = string
  default     = "v5.5.1"
}

variable "database" {
  description = "\"local\": Postgres in a container on the server (staging). \"rds\": managed RDS with daily backups (production)."
  type        = string
  default     = "local"
  validation {
    condition     = contains(["local", "rds"], var.database)
    error_message = "database must be \"local\" or \"rds\"."
  }
}

variable "db_instance_class" {
  description = "RDS size. db.t4g.micro (2 vCPU burst, 1 GB) is plenty at launch."
  type        = string
  default     = "db.t4g.micro"
}

variable "postgres_version" {
  description = "RDS Postgres major version (AWS picks the current minor)."
  type        = string
  default     = "17"
}

variable "db_backup_retention_days" {
  description = "Days of automated backups (point-in-time restore window). AWS Free plan accounts may cap this; upgrade to the Paid plan before production."
  type        = number
  default     = 7
}

variable "redirect_domains" {
  description = "Names in dns_zone pointed at this server and redirected (302) to `domain`, e.g. the bare domain while only staging is live. Remove before another stack takes them."
  type        = list(string)
  default     = []
}

variable "extra_dns_records" {
  description = "Additional records in dns_zone, e.g. MX for inbound mail forwarding. One entry per name+type (TXT values go in one entry's records list)."
  type = list(object({
    name    = string
    type    = string
    ttl     = optional(number, 3600)
    records = list(string)
  }))
  default = []
}
