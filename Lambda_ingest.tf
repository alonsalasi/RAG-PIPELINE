# Build and Push Ingestion Docker Image to ECR
resource "null_resource" "build_and_push_ingestion_image" {
  triggers = {
    dockerfile_hash   = filemd5("${path.module}/Lambda/ingestion.Dockerfile")
    requirements_hash = filemd5("${path.module}/Lambda/ingestion_requirements.txt")
    handler_hash      = filemd5("${path.module}/Lambda/lambda_ingest_handler.py")
    worker_hash       = filemd5("${path.module}/Lambda/worker.py")
    repo_url          = aws_ecr_repository.ingestion_lambda_repo.repository_url
    rebuild_trigger   = "2024-01-15-001"
  }
  
  provisioner "local-exec" {
    interpreter = ["powershell", "-Command"]
    command = "docker build --platform linux/amd64 --provenance=false -t ${aws_ecr_repository.ingestion_lambda_repo.repository_url}:latest -f Lambda/ingestion.Dockerfile ./Lambda"
  }
  
  provisioner "local-exec" {
    interpreter = ["powershell", "-Command"]
    command = "docker push ${aws_ecr_repository.ingestion_lambda_repo.repository_url}:latest"
  }

  depends_on = [aws_ecr_repository.ingestion_lambda_repo, null_resource.build_and_push_agent_image]
}

resource "aws_lambda_function" "ingestion_worker" {
  function_name = "${var.project_name}-ingestion-worker"
  description   = "Version: ${var.ingestion_version}"
  role          = aws_iam_role.lambda_ingestion_role.arn
  timeout       = 900
  memory_size   = 3008

  package_type = "Image"
  image_uri    = "${aws_ecr_repository.ingestion_lambda_repo.repository_url}:latest"
  kms_key_arn  = aws_kms_key.agent_encryption.arn

  dynamic "vpc_config" {
    for_each = var.enable_lambda_vpc ? [1] : []
    content {
      subnet_ids         = aws_subnet.private[*].id
      security_group_ids = [aws_security_group.lambda_sg[0].id]
    }
  }

  environment {
    variables = {
      S3_BUCKET        = aws_s3_bucket.rag_documents.bucket
      MAX_PARALLEL_OCR = 4
      DPI              = 150
      SECRETS_ARN      = aws_secretsmanager_secret.bedrock_config.arn
    }
  }

  tracing_config {
    mode = "Active"
  }

  dead_letter_config {
    target_arn = aws_sqs_queue.ingestion_dlq.arn
  }

  depends_on = [
    null_resource.build_and_push_ingestion_image
  ]
}

# Allow S3 to invoke ingestion Lambda
resource "aws_lambda_permission" "allow_s3_invoke" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingestion_worker.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.rag_documents.arn
}
