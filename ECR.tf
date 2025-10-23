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

output "ingestion_lambda_ecr_repository_url" {
  description = "The URL of the ECR repository for the ingestion Lambda image."
  value       = aws_ecr_repository.ingestion_lambda_repo.repository_url
}