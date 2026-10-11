# ── Managed Postgres (production) ──
# Staging runs Postgres in a container on the server: cheap and disposable. Production uses RDS instead: daily
# automated backups with point-in-time restore, encrypted storage, and data that survives the server being replaced.
# Only the app server can reach it (security group), and it has no public address.

locals {
  rds = var.database == "rds"
}

resource "random_password" "db" {
  count   = local.rds ? 1 : 0
  length  = 40
  special = false # used inside a libpq URL; letters and digits avoid any escaping
}

resource "aws_security_group" "db" {
  count       = local.rds ? 1 : 0
  name        = "${local.name}-db"
  description = "Postgres from the app server only."
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description     = "Postgres from the app server"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }
}

resource "aws_db_subnet_group" "db" {
  count      = local.rds ? 1 : 0
  name       = "${local.name}-db"
  subnet_ids = data.aws_subnets.default.ids
}

resource "aws_db_instance" "main" {
  count          = local.rds ? 1 : 0
  identifier     = "${local.name}-db"
  engine         = "postgres"
  engine_version = var.postgres_version
  instance_class = var.db_instance_class

  allocated_storage     = 20
  max_allocated_storage = 100 # grows on its own when nearly full
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = "provok"
  username = "provok"
  password = random_password.db[0].result

  db_subnet_group_name   = aws_db_subnet_group.db[0].name
  vpc_security_group_ids = [aws_security_group.db[0].id]
  publicly_accessible    = false
  multi_az               = false # a standby doubles the price; revisit when downtime costs more than that

  backup_retention_period = var.db_backup_retention_days
  backup_window           = "20:00-21:00"         # 01:30–02:30 IST, the quietest hour
  maintenance_window      = "sun:21:00-sun:22:00" # right after, Sunday
  copy_tags_to_snapshot   = true

  auto_minor_version_upgrade   = true
  performance_insights_enabled = false

  # Deleting the database takes two deliberate steps: turn this off, then destroy. A final snapshot is kept.
  deletion_protection       = true
  skip_final_snapshot       = false
  final_snapshot_identifier = "${local.name}-db-final"

  tags = {
    Name = "${local.name}-db"
  }
}
