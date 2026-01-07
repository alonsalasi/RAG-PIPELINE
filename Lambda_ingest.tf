# Build and Push Ingestion Docker Image to ECR
resource "null_resource" "build_and_push_ingestion_image" {
  triggers = {
    dockerfile_hash      = filemd5("${path.module}/Lambda/ingestion.Dockerfile")
    requirements_hash    = filemd5("${path.module}/Lambda/ingestion_requirements.txt")
    handler_hash         = filemd5("${path.module}/Lambda/lambda_ingest_handler.py")
    worker_hash          = filemd5("${path.module}/Lambda/worker.py")
    semantic_chunker_hash = filemd5("${path.module}/Lambda/semantic_chunker.py")
    office_converter_hash = filemd5("${path.module}/Lambda/office_converter.py")
    image_analysis_hash  = filemd5("${path.module}/Lambda/image_analysis.py")
    repo_url             = aws_ecr_repository.ingestion_lambda_repo.repository_url
    rebuild_trigger      = "2025-03-15-s3client-fix"
  }
  
  provisioner "local-exec" {
    interpreter = ["powershell", "-Command"]
    command = "cd Lambda; .\\ingestion_cache_build_push.bat; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }"
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
      PROJECT_NAME     = var.project_name
    }
  }

  tracing_config {
    mode = "Active"
  }

  dead_letter_config {
    target_arn = aws_sqs_queue.ingestion_dlq.arn
  }
  
  reserved_concurrent_executions = 10

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
