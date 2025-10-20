resource "aws_ecr_repository" "rag_repository" {
  name                 = "${var.project_name}/rag-app-${var.environment}"
  image_tag_mutability = "MUTABLE"

  # Configure image scanning and tag immutability for security (optional)
  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name = "${var.project_name}-rag-app-ecr-${var.environment}"
  }
}

data "aws_iam_policy_document" "ecr_repository_policy" {
  statement {
    sid    = "AllowPushPull"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }

    actions = [
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
      "ecr:BatchCheckLayerAvailability",
      "ecr:PutImage",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
      "ecr:GetAuthorizationToken" # Required for pushing/pulling
    ]
  }
}

resource "aws_ecr_repository_policy" "rag_repository_policy" {
  repository = aws_ecr_repository.rag_repository.name
  policy     = data.aws_iam_policy_document.ecr_repository_policy.json
}

data "aws_caller_identity" "current" {}
