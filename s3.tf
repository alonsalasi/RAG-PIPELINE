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

resource "aws_s3_bucket_lifecycle_configuration" "rag_documents_lifecycle" {
  bucket = aws_s3_bucket.rag_documents.id

  rule {
    id     = "delete-incomplete-uploads"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  rule {
    id     = "autofill-sessions-cleanup"
    status = "Enabled"

    filter {
      prefix = "document-autofill/sessions/"
    }

    expiration {
      days = 1
    }
  }

  rule {
    id     = "autofill-completed-cleanup"
    status = "Enabled"

    filter {
      prefix = "document-autofill/completed/"
    }

    expiration {
      days = 3
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

  lambda_function {
    lambda_function_arn = aws_lambda_function.ingestion_worker.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "uploads/"
    filter_suffix       = ".pptx"
  }

  lambda_function {
    lambda_function_arn = aws_lambda_function.ingestion_worker.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "uploads/"
    filter_suffix       = ".docx"
  }

  lambda_function {
    lambda_function_arn = aws_lambda_function.ingestion_worker.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "uploads/"
    filter_suffix       = ".xlsx"
  }

  lambda_function {
    lambda_function_arn = aws_lambda_function.ingestion_worker.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "uploads/"
    filter_suffix       = ".jpg"
  }

  lambda_function {
    lambda_function_arn = aws_lambda_function.ingestion_worker.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "uploads/"
    filter_suffix       = ".jpeg"
  }

  lambda_function {
    lambda_function_arn = aws_lambda_function.ingestion_worker.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "uploads/"
    filter_suffix       = ".png"
  }

  lambda_function {
    lambda_function_arn = aws_lambda_function.ingestion_worker.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "uploads/"
    filter_suffix       = ".tiff"
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