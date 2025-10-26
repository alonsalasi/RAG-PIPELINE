resource "aws_ecr_repository" "ingestion_lambda_repo" {
  name                 = "${var.project_name}-ingestion-lambda-${var.environment}"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name        = "RAG Ingestion Lambda Repository"
    Environment = var.environment
  }
}

resource "aws_ecr_repository" "api_lambda_repo" {
  name                 = "${var.project_name}-api-lambda-${var.environment}"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name        = "RAG Ingestion Lambda Repository"
    Environment = var.environment
  }
}