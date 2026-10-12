locals {
  name        = "provok-${var.environment}"
  account_id  = data.aws_caller_identity.current.account_id
  site_domain = var.domain != "" ? var.domain : "${replace(aws_eip.app.public_ip, ".", "-")}.sslip.io"
  registry    = "${local.account_id}.dkr.ecr.${var.region}.amazonaws.com"
  env_param   = "/provok/${var.environment}/env"
}

data "aws_caller_identity" "current" {}

# ── Network: the default VPC's public subnets. No NAT gateway (it alone would cost more than the server). ──

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}

resource "aws_security_group" "app" {
  name        = "${local.name}-app"
  description = "HTTP/HTTPS in, everything out. No SSH: shell access is through SSM Session Manager."
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description      = "HTTP (ACME challenge + redirect to HTTPS)"
    from_port        = 80
    to_port          = 80
    protocol         = "tcp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }
  ingress {
    description      = "HTTPS"
    from_port        = 443
    to_port          = 443
    protocol         = "tcp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }
  ingress {
    description      = "HTTP/3"
    from_port        = 443
    to_port          = 443
    protocol         = "udp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }
  egress {
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }
}

# ── Server ──

data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

resource "aws_instance" "app" {
  ami                    = data.aws_ssm_parameter.al2023.insecure_value
  instance_type          = var.instance_type
  subnet_id              = data.aws_subnets.default.ids[0]
  vpc_security_group_ids = [aws_security_group.app.id]
  iam_instance_profile   = aws_iam_instance_profile.app.name
  user_data              = templatefile("${path.module}/user-data.sh", { compose_version = var.compose_version })

  metadata_options {
    http_tokens                 = "required" # IMDSv2 only
    http_put_response_hop_limit = 2          # containers need one extra hop to reach the role credentials
  }

  root_block_device {
    volume_size = var.root_volume_gb
    volume_type = "gp3"
    encrypted   = true
  }

  # t3 defaults to "unlimited", which bills for sustained CPU above baseline. Throttle instead of surprise charges.
  credit_specification {
    cpu_credits = "standard"
  }

  tags = {
    Name = "${local.name}-app"
  }

  lifecycle {
    # A newer AMI or bootstrap script must not silently replace the server (and its staging database).
    ignore_changes = [ami, user_data]
  }
}

resource "aws_eip" "app" {
  domain = "vpc"
  tags = {
    Name = "${local.name}-app"
  }
}

resource "aws_eip_association" "app" {
  instance_id   = aws_instance.app.id
  allocation_id = aws_eip.app.id
}

# ── Images ──

resource "aws_ecr_repository" "app" {
  for_each             = toset(["api", "web"])
  name                 = "${local.name}/${each.key}"
  image_tag_mutability = "IMMUTABLE" # tags are commit SHAs

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "app" {
  for_each   = aws_ecr_repository.app
  repository = each.value.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the 15 most recent images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 15 }
      action       = { type = "expire" }
    }]
  })
}

# ── Media (avatars, highlight clips and post images are public; recordings stay private) ──

resource "aws_s3_bucket" "media" {
  bucket = "${local.name}-media-${local.account_id}"
}

resource "aws_s3_bucket_ownership_controls" "media" {
  bucket = aws_s3_bucket.media.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "media" {
  bucket                  = aws_s3_bucket.media.id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = false # the policy below makes two prefixes readable
  restrict_public_buckets = false
}

resource "aws_s3_bucket_policy" "media_public_read" {
  bucket     = aws_s3_bucket.media.id
  depends_on = [aws_s3_bucket_public_access_block.media]
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "PublicReadAvatarsClipsAndPostImages"
      Effect    = "Allow"
      Principal = "*"
      Action    = "s3:GetObject"
      Resource = [
        "${aws_s3_bucket.media.arn}/avatars/*",
        "${aws_s3_bucket.media.arn}/clips/*",
        "${aws_s3_bucket.media.arn}/posts/*",
      ]
    }]
  })
}

# ── Deploy bundles (compose file, Caddyfile, deploy script per commit) ──

resource "aws_s3_bucket" "deploy" {
  bucket = "${local.name}-deploy-${local.account_id}"
}

resource "aws_s3_bucket_public_access_block" "deploy" {
  bucket                  = aws_s3_bucket.deploy.id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "deploy" {
  bucket = aws_s3_bucket.deploy.id
  rule {
    id     = "expire-old-bundles"
    status = "Enabled"
    filter {}
    expiration {
      days = 30
    }
  }
}

# ── Email (SES) ──

resource "aws_sesv2_email_identity" "domain" {
  count          = var.ses_domain != "" ? 1 : 0
  email_identity = var.ses_domain
}

resource "aws_sesv2_email_identity" "sender" {
  for_each       = toset(var.ses_sender_emails)
  email_identity = each.value
}

# ── Non-secret deploy settings, read by the GitHub deploy workflow ──

resource "aws_ssm_parameter" "deploy_config" {
  name = "/provok/${var.environment}/deploy"
  type = "String"
  value = jsonencode({
    site_domain   = local.site_domain
    instance_id   = aws_instance.app.id
    deploy_bucket = aws_s3_bucket.deploy.bucket
    registry      = local.registry
    api_repo      = aws_ecr_repository.app["api"].name
    web_repo      = aws_ecr_repository.app["web"].name
    env_parameter = local.env_param
  })
}
