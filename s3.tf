# Frontend bucket (no KMS for CloudFront compatibility)
resource "aws_s3_bucket" "frontend" {
  bucket = "${var.project_name}-frontend-${var.environment}"
  
  tags = {
    Name = "${var.project_name}-frontend"
  }
}

resource "aws_s3_bucket_public_access_block" "frontend_block" {
  bucket                  = aws_s3_bucket.frontend.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket" "rag_documents" {
  bucket = "${var.project_name}-rag-documents-${var.environment}"
  
  tags = {
    Name = "${var.project_name}-rag-documents-${var.environment}"
    Environment = var.environment
    CostCenter  = "RAG-Production"
    Compliance  = "Required"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "rag_documents_encryption" {
  bucket = aws_s3_bucket.rag_documents.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.agent_encryption.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_versioning" "rag_documents_versioning" {
  bucket = aws_s3_bucket.rag_documents.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "rag_documents_lifecycle" {
  bucket = aws_s3_bucket.rag_documents.id

  rule {
    id     = "archive-old-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_transition {
      noncurrent_days = 30
      storage_class   = "STANDARD_IA"
    }

    noncurrent_version_transition {
      noncurrent_days = 60
      storage_class   = "GLACIER_IR"
    }

    noncurrent_version_expiration {
      noncurrent_days = 120
    }
  }

  rule {
    id     = "delete-incomplete-uploads"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

resource "aws_s3_bucket_public_access_block" "rag_documents_block" {
  bucket = aws_s3_bucket.rag_documents.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_logging" "rag_documents_logging" {
  bucket = aws_s3_bucket.rag_documents.id

  target_bucket = aws_s3_bucket.audit_logs.id
  target_prefix = "s3-access-logs/"
}

resource "aws_s3_bucket_cors_configuration" "rag_documents_cors" {
  bucket = aws_s3_bucket.rag_documents.id

  cors_rule {
    allowed_methods = ["PUT", "POST", "GET", "HEAD"]
    allowed_origins = ["https://${aws_cloudfront_distribution.rag_frontend_cdn.domain_name}"]
    allowed_headers = ["Content-Type", "Content-MD5", "Content-Disposition"]
    expose_headers = ["ETag", "Content-Length"]
    max_age_seconds = 3000
  }
}

# S3 Event Notification to trigger ingestion Lambda
resource "aws_s3_bucket_notification" "rag_documents_notification" {
  bucket = aws_s3_bucket.rag_documents.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.ingestion_worker.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "uploads/"
    filter_suffix       = ".pdf"
  }

  depends_on = [
    aws_lambda_permission.allow_s3_invoke,
    aws_lambda_function.ingestion_worker
  ]

  lifecycle {
    replace_triggered_by = [
      aws_lambda_function.ingestion_worker
    ]
  }
}