# Reference infrastructure-as-code for Phase 8's AWS migration - see README.md in this
# directory. This has been validated locally (`terraform init`, `terraform validate`,
# `terraform fmt -check`) but NEVER `terraform apply`d against a real AWS account - no
# AWS credentials exist anywhere in this project's development environment.

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# The default VPC/subnets are used rather than defining a custom VPC - appropriate for a
# small single-instance portfolio deployment; a real production system would likely want
# its own VPC with private subnets for RDS, but that's a scope decision beyond what this
# reference architecture needs to demonstrate.
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }
}

locals {
  common_tags = {
    Project = var.project_name
  }
}
