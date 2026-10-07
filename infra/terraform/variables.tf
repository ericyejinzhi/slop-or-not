variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Short name used to prefix/tag all resources"
  type        = string
  default     = "slop-or-not"
}

variable "thumbnails_bucket_name" {
  description = "Globally-unique S3 bucket name for thumbnails - S3 bucket names are unique across ALL of AWS, not just your account, so the default below must be changed before ever applying this."
  type        = string
  default     = "slop-or-not-thumbnails-CHANGE-ME"
}

variable "models_bucket_name" {
  description = "Globally-unique S3 bucket name for published model artifacts (see `slop model publish`) - unique across ALL of AWS, so the default below must be changed before ever applying this."
  type        = string
  default     = "slop-or-not-models-CHANGE-ME"
}

variable "db_name" {
  description = "Postgres database name"
  type        = string
  default     = "slopornot"
}

variable "db_username" {
  description = "RDS master username"
  type        = string
  default     = "slop"
}

variable "db_password" {
  description = "RDS master password - pass via TF_VAR_db_password or an untracked .tfvars file, never a literal default committed to git."
  type        = string
  sensitive   = true
}

variable "db_instance_class" {
  description = "RDS instance class - db.t4g.micro is the cheapest option that still supports pgvector"
  type        = string
  default     = "db.t4g.micro"
}

variable "db_engine_version" {
  description = "Postgres version - must be 13.10+/14.7+/15.2+/16.1+ for pgvector support (AWS RDS docs)"
  type        = string
  default     = "16.4"
}

variable "app_instance_type" {
  description = "EC2 instance type running api+web via docker-compose"
  type        = string
  default     = "t3.small"
}

variable "ssh_ingress_cidr" {
  description = "CIDR allowed to SSH into the app instance - set this to YOUR_IP/32 before ever applying; the default is deliberately a non-functional placeholder, not an open door."
  type        = string
  default     = "203.0.113.1/32"
}
