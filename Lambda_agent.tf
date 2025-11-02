# Lambda_agent.tf

# =========================================================
# Build and Push Docker Image to ECR
# =========================================================
resource "null_resource" "build_and_push_agent_image" {
  triggers = {
    dockerfile_hash   = filemd5("${path.module}/Lambda/agent.Dockerfile")
    requirements_hash = filemd5("${path.module}/Lambda/agent_requirements.txt")
    source_code_hash  = filemd5("${path.module}/Lambda/agent_executor.py")
    repo_url          = aws_ecr_repository.agent_lambda_repo.repository_url
    rebuild_trigger   = "2024-01-15-all-optimizations"
  }

  provisioner "local-exec" {
    interpreter = ["powershell", "-Command"]
    command = "cd Lambda; .\\agent_no_cache_build_push.bat; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }"
  }

  depends_on = [aws_ecr_repository.agent_lambda_repo]
}

# =========================================================
# Lambda Function for Bedrock Agent Executor
# =========================================================
resource "aws_lambda_function" "agent_executor" {
  function_name = "${var.project_name}-agent-executor"
  role          = aws_iam_role.lambda_agent_role.arn
  package_type  = "Image"
  timeout       = 90
  memory_size   = 3008

  image_uri = "${aws_ecr_repository.agent_lambda_repo.repository_url}:latest"
  kms_key_arn = aws_kms_key.agent_encryption.arn

  # VPC Configuration (conditional based on security requirements)
  dynamic "vpc_config" {
    for_each = var.enable_lambda_vpc ? [1] : []
    content {
      subnet_ids         = aws_subnet.private[*].id
      security_group_ids = [aws_security_group.lambda_sg[0].id]
    }
  }

  environment {
    variables = {
      S3_BUCKET                = "pdfquery-rag-documents-production"
      VECTOR_STORE_PATH        = "vector_store/default"
      SECRETS_ARN              = aws_secretsmanager_secret.bedrock_config.arn
      BEDROCK_AGENT_ID         = aws_bedrockagent_agent.rag_agent.agent_id
      BEDROCK_AGENT_ALIAS_ID   = "19RBXR8RAY"
      SES_SENDER_EMAIL         = var.ses_sender_email
      EMBEDDINGS_MODEL_ID      = "cohere.embed-multilingual-v3"
      FORCE_UPDATE             = "2025-11-02-fix-env-vars-v2"
    }
  }



  tracing_config {
    mode = "Active"
  }

  dead_letter_config {
    target_arn = aws_sqs_queue.agent_dlq.arn
  }

  depends_on = [
    null_resource.build_and_push_agent_image,
    aws_iam_role.lambda_agent_role
  ]

  tags = {
    Name = "${var.project_name}-agent-executor"
  }
}