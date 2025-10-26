##############################################
# Lambda: API Query Service (Container Image)
##############################################

# --- Lambda Function (using ECR image) ---
resource "aws_lambda_function" "api_query_service" {
  function_name = "${var.project_name}-api-query-service"
  description   = "RAG Query API Lambda (container image with FAISS + LangChain)"
  role          = aws_iam_role.lambda_api_role.arn

  # Use container image instead of ZIP
  package_type  = "Image"
  image_uri    = "${aws_ecr_repository.api_lambda_repo.repository_url}:${var.api_image_tag}"
  timeout       = 90
  memory_size   = 1024

  vpc_config {
    subnet_ids         = aws_subnet.private.*.id
    security_group_ids = [aws_security_group.lambda_sg.id]
  }

  environment {
    variables = {
      S3_BUCKET             = aws_s3_bucket.rag_documents.bucket
      PATH_PREFIX_TO_REMOVE = "default"
    }
  }

  depends_on = [
    aws_iam_role.lambda_api_role
  ]

  tags = {
    Name        = "${var.project_name}-api-query-service"
    Environment = var.environment
  }
}
