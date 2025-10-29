resource "aws_lambda_function" "ingestion_worker" {
  function_name = "${var.project_name}-ingestion-worker"
  description   = "Version: ${var.ingestion_version}"
  role          = aws_iam_role.lambda_ingestion_role.arn
  timeout       = 900
  memory_size   = 3008  # Maximum allowed for Lambda

  package_type = "Image"
  image_uri    = "${aws_ecr_repository.ingestion_lambda_repo.repository_url}:${var.ingestion_image_tag}"
  kms_key_arn  = aws_kms_key.agent_encryption.arn

  # VPC Configuration (conditional based on security requirements)
  dynamic "vpc_config" {
    for_each = var.enable_lambda_vpc ? [1] : []
    content {
      subnet_ids         = aws_subnet.private[*].id
      security_group_ids = [aws_security_group.lambda_sg.id]
    }
  }

  environment {
    variables = {
      S3_BUCKET        = aws_s3_bucket.rag_documents.bucket
      AWS_REGION       = data.aws_region.current.name
      MAX_PARALLEL_OCR = 4
      DPI              = 150
      SECRETS_ARN      = aws_secretsmanager_secret.bedrock_config.arn
    }
  }

  tracing_config {
    mode = "Active"
  }

  dead_letter_config {
    target_arn = aws_sqs_queue.lambda_dlq.arn
  }

  depends_on = [
    aws_ecr_repository.ingestion_lambda_repo,
    aws_cloudwatch_log_group.lambda_ingestion_logs
  ]
}
