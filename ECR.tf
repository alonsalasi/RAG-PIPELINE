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

# API Lambda ECR repository removed - functionality moved to agent Lambda

resource "aws_ecr_repository" "agent_lambda_repo" {
  name                 = "${var.project_name}-agent-lambda-${var.environment}"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name        = "RAG Agent Lambda Repository"
    Environment = var.environment
  }
}