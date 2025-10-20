# S3 Bucket for Terraform Remote State
resource "aws_s3_bucket" "terraform_state" {
  bucket = "${var.project_name}-tf-state-${var.aws_region}"

  tags = {
    Name = "${var.project_name}-tf-state"
  }
}

# Enable versioning (good practice for state file recovery)
resource "aws_s3_bucket_versioning" "terraform_state_versioning" {
  bucket = aws_s3_bucket.terraform_state.id
  versioning_configuration {
    status = "Enabled"
  }
}

# DynamoDB Table for State Locking
# This is crucial for preventing concurrent modifications to the state file.
resource "aws_dynamodb_table" "terraform_locks" {
  name           = "${var.project_name}-tf-locks"
  hash_key       = "LockID"
  read_capacity  = 5
  write_capacity = 5

  attribute {
    name = "LockID"
    type = "S"
  }

  tags = {
    Name = "${var.project_name}-tf-locks"
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
