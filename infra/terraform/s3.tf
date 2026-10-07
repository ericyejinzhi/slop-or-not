# Thumbnails bucket - replaces MinIO (see src/sloppy/storage.py, docs/writeups/phase-8
# stage 1). Private (no public bucket policy/ACLs) - the app reads/writes it via
# presigned URLs or the app instance's IAM role, never via public bucket access.

resource "aws_s3_bucket" "thumbnails" {
  bucket = var.thumbnails_bucket_name
  tags   = local.common_tags
}

resource "aws_s3_bucket_public_access_block" "thumbnails" {
  bucket = aws_s3_bucket.thumbnails.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "thumbnails" {
  bucket = aws_s3_bucket.thumbnails.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Models bucket - published model artifacts (src/sloppy/models/artifact_store.py). Private,
# like the thumbnails bucket, but the app's instance role gets READ-ONLY access (see
# ec2.tf): model.joblib is a pickle, so whoever can write here can run code on any server
# that loads from it. Publishing (`slop model publish`) is done with the owner's own AWS
# credentials, never from the app instance.

resource "aws_s3_bucket" "models" {
  bucket = var.models_bucket_name
  tags   = local.common_tags
}

resource "aws_s3_bucket_public_access_block" "models" {
  bucket = aws_s3_bucket.models.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "models" {
  bucket = aws_s3_bucket.models.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
