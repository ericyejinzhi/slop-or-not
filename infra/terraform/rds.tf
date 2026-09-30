# Replaces the local docker-compose `postgres` service (pgvector/pgvector:pg16) with a
# managed RDS Postgres instance - pgvector is supported on RDS as of Postgres
# 13.10+/14.7+/15.2+/16.1+, but enabling it is a SQL-level `CREATE EXTENSION vector;`
# run against the database AFTER it exists, not a Terraform resource - see
# docs/writeups/phase-8's Terraform stage and docs/writeups/TODO.md for that manual step.

resource "aws_db_subnet_group" "postgres" {
  name       = "${var.project_name}-db-subnets"
  subnet_ids = data.aws_subnets.default.ids
  tags       = local.common_tags
}

# Not publicly accessible and only reachable from the app instance's own security group
# - RDS should never be exposed directly to the internet for this kind of deployment.
resource "aws_security_group" "rds" {
  name        = "${var.project_name}-rds-sg"
  description = "Allow Postgres access from the app instance only"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description     = "Postgres from the app instance"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.common_tags
}

resource "aws_db_instance" "postgres" {
  identifier              = "${var.project_name}-db"
  engine                  = "postgres"
  engine_version          = var.db_engine_version
  instance_class          = var.db_instance_class
  allocated_storage       = 20
  db_name                 = var.db_name
  username                = var.db_username
  password                = var.db_password
  db_subnet_group_name    = aws_db_subnet_group.postgres.name
  vpc_security_group_ids  = [aws_security_group.rds.id]
  publicly_accessible     = false
  skip_final_snapshot     = true
  backup_retention_period = 1

  tags = local.common_tags
}
