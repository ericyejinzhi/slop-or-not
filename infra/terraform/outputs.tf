output "thumbnails_bucket_name" {
  description = "S3 bucket name - set as S3_BUCKET_THUMBNAILS in a production .env"
  value       = aws_s3_bucket.thumbnails.bucket
}

output "models_bucket_name" {
  description = "S3 bucket name for model artifacts - set as S3_BUCKET_MODELS in a production .env, and publish with `slop model publish`"
  value       = aws_s3_bucket.models.bucket
}

output "rds_endpoint" {
  description = "RDS Postgres endpoint (host:port) - set as POSTGRES_HOST/POSTGRES_PORT"
  value       = aws_db_instance.postgres.endpoint
}

output "app_public_ip" {
  description = "Public IP of the EC2 instance running api+web via docker-compose"
  value       = aws_instance.app.public_ip
}
