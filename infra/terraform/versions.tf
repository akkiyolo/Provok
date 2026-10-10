terraform {
  required_version = ">= 1.10" # S3 backend native locking (use_lockfile)

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.65.0"
    }
  }

  # Partial config: bucket/key/region are passed to `terraform init` (see infra/README.md).
  backend "s3" {}
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "provok"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
