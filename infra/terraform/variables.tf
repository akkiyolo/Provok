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
