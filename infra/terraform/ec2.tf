# Single EC2 instance running `api` + `web` via docker-compose (the roadmap's own
# "simplest" option, over ECS) - see docker-compose.yml. Grants S3 access via an IAM
# instance role rather than long-lived access keys - src/sloppy/storage.py's
# get_s3_client() falls back to boto3's default credential chain (which resolves an
# instance role automatically) when S3_ACCESS_KEY/SECRET are left unset.

resource "aws_security_group" "app" {
  name        = "${var.project_name}-app-sg"
  description = "Public HTTP for the web/nginx container; SSH restricted to a single IP"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "web (nginx, proxies /api/* to the api container internally)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "SSH - ssh_ingress_cidr must be set to your own IP before ever applying this, never left at its placeholder default"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.ssh_ingress_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.common_tags
}

resource "aws_iam_role" "app" {
  name = "${var.project_name}-app-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })

  tags = local.common_tags
}

# Least-privilege: only the S3 actions this app actually calls (get/put/list on the
# thumbnails bucket - see src/sloppy/storage.py, src/sloppy/ingest/thumbnails.py), scoped
# to that one bucket, not "*".
resource "aws_iam_role_policy" "app_s3_access" {
  name = "${var.project_name}-app-s3-access"
  role = aws_iam_role.app.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket",
      ]
      Resource = [
        aws_s3_bucket.thumbnails.arn,
        "${aws_s3_bucket.thumbnails.arn}/*",
      ]
    }]
  })
}

resource "aws_iam_instance_profile" "app" {
  name = "${var.project_name}-app-profile"
  role = aws_iam_role.app.name
}

resource "aws_instance" "app" {
  ami                    = data.aws_ami.amazon_linux.id
  instance_type          = var.app_instance_type
  subnet_id              = data.aws_subnets.default.ids[0]
  vpc_security_group_ids = [aws_security_group.app.id]
  iam_instance_profile   = aws_iam_instance_profile.app.name

  # A real deployment: install Docker + the Compose plugin, clone the repo, `cp
  # .env.example .env` and fill in the RDS endpoint/S3 bucket/AWS_REGION (leaving
  # S3_ACCESS_KEY/SECRET blank so this instance's IAM role is used - see
  # docs/writeups/phase-8), then `docker compose up -d --build api web`. Deliberately not
  # automated as user_data here - this reference IaC is never applied, and baking a real
  # deployment script into a Terraform default would be untested, unreviewed shell code
  # nobody has actually run.
  tags = merge(local.common_tags, { Name = "${var.project_name}-app" })
}
