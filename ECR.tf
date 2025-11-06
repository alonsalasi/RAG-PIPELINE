resource "aws_ecr_repository" "ingestion_lambda_repo" {
  name                 = "${var.project_name}-ingestion-lambda-${var.environment}"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name        = "${var.project_name}-ingestion-lambda-repository"
    Environment = var.environment
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_ecr_lifecycle_policy" "ingestion_lambda_policy" {
  repository = aws_ecr_repository.ingestion_lambda_repo.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 3 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 3
      }
      action = {
        type = "expire"
      }
    }]
  })
}

# API Lambda ECR repository removed - functionality moved to agent Lambda

resource "aws_ecr_repository" "agent_lambda_repo" {
  name                 = "${var.project_name}-agent-lambda-${var.environment}"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name        = "${var.project_name}-agent-lambda-repository"
    Environment = var.environment
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_ecr_lifecycle_policy" "agent_lambda_policy" {
  repository = aws_ecr_repository.agent_lambda_repo.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 3 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 3
      }
      action = {
        type = "expire"
      }
    }]
  })
}