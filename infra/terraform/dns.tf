# ── DNS (Route 53) ──
# The zone is one per account, like the GitHub OIDC provider: the first stack creates it, later ones look it up.
# After the first apply, set the registrar's nameservers to `terraform output dns_nameservers`.

resource "aws_route53_zone" "main" {
  count = var.dns_zone != "" && var.create_dns_zone ? 1 : 0
  name  = var.dns_zone
}

data "aws_route53_zone" "main" {
  count = var.dns_zone != "" && !var.create_dns_zone ? 1 : 0
  name  = var.dns_zone
}

locals {
  zone_id = var.dns_zone == "" ? "" : (var.create_dns_zone ? aws_route53_zone.main[0].zone_id : data.aws_route53_zone.main[0].zone_id)
  # SES records live in the zone only when the sending domain is (or is under) the zone.
  ses_in_zone = var.dns_zone != "" && var.ses_domain != "" && endswith(var.ses_domain, var.dns_zone)
}

resource "aws_route53_record" "site" {
  count   = var.dns_zone != "" && var.domain != "" ? 1 : 0
  zone_id = local.zone_id
  name    = var.domain
  type    = "A"
  ttl     = 300
  records = [aws_eip.app.public_ip]
}

# Extra names that land on this server and are redirected to `domain` by Caddy (REDIRECT_DOMAINS in the server env).
resource "aws_route53_record" "redirect" {
  for_each = var.dns_zone == "" ? toset([]) : toset(var.redirect_domains)
  zone_id  = local.zone_id
  name     = each.value
  type     = "A"
  ttl      = 300
  records  = [aws_eip.app.public_ip]
}

# ── Email authentication for the SES domain: DKIM, SPF (via a custom MAIL FROM) and DMARC ──

resource "aws_route53_record" "ses_dkim" {
  count   = local.ses_in_zone ? 3 : 0
  zone_id = local.zone_id
  name    = "${aws_sesv2_email_identity.domain[0].dkim_signing_attributes[0].tokens[count.index]}._domainkey.${var.ses_domain}"
  type    = "CNAME"
  ttl     = 1800
  records = ["${aws_sesv2_email_identity.domain[0].dkim_signing_attributes[0].tokens[count.index]}.dkim.amazonses.com"]
}

resource "aws_sesv2_email_identity_mail_from_attributes" "domain" {
  count                  = local.ses_in_zone ? 1 : 0
  email_identity         = aws_sesv2_email_identity.domain[0].email_identity
  mail_from_domain       = "mail.${var.ses_domain}"
  behavior_on_mx_failure = "USE_DEFAULT_VALUE"
}

resource "aws_route53_record" "mail_from_mx" {
  count   = local.ses_in_zone ? 1 : 0
  zone_id = local.zone_id
  name    = "mail.${var.ses_domain}"
  type    = "MX"
  ttl     = 1800
  records = ["10 feedback-smtp.${var.region}.amazonses.com"]
}

resource "aws_route53_record" "mail_from_spf" {
  count   = local.ses_in_zone ? 1 : 0
  zone_id = local.zone_id
  name    = "mail.${var.ses_domain}"
  type    = "TXT"
  ttl     = 1800
  records = ["v=spf1 include:amazonses.com ~all"]
}

# Monitor-only to start; tighten to quarantine once mail is confirmed to pass.
resource "aws_route53_record" "dmarc" {
  count   = local.ses_in_zone ? 1 : 0
  zone_id = local.zone_id
  name    = "_dmarc.${var.ses_domain}"
  type    = "TXT"
  ttl     = 1800
  records = ["v=DMARC1; p=none;"]
}

# ── Other records (e.g. inbound mail forwarding, site verifications), from extra_dns_records ──

resource "aws_route53_record" "extra" {
  for_each = var.dns_zone == "" ? {} : { for r in var.extra_dns_records : "${r.name}|${r.type}" => r }
  zone_id  = local.zone_id
  name     = each.value.name
  type     = each.value.type
  ttl      = each.value.ttl
  records  = each.value.records
}
