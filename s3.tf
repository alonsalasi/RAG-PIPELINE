resource "aws_s3_bucket" "terraform_state" {
  bucket = "${var.project_name}-tf-state-${var.aws_region}"

  tags = {
    Name = "${var.project_name}-tf-state"
  }
}

resource "aws_s3_bucket_versioning" "terraform_state_versioning" {
  bucket = aws_s3_bucket.terraform_state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket" "rag_documents" {
  bucket = "${var.project_name}-rag-documents-${var.environment}"
  
  tags = {
    Name = "${var.project_name}-rag-documents-${var.environment}"
  }
}

resource "aws_s3_bucket_public_access_block" "rag_documents_block" {
  bucket = aws_s3_bucket.rag_documents.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_cors_configuration" "rag_documents_cors" {
  bucket = aws_s3_bucket.rag_documents.id

  cors_rule {
    allowed_methods = ["PUT", "POST", "GET", "HEAD"]
    allowed_origins = ["https://d2h33zz3k8plgu.cloudfront.net"] 
    allowed_headers = ["*"] 
    expose_headers = ["ETag", "Content-Length"]
    max_age_seconds = 3000
  }
}