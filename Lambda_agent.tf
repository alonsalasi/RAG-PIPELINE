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
    rebuild_trigger   = "2024-01-15-019"
  }

  # --- START WINDOWS FIX ---
  provisioner "local-exec" {
    # Use PowerShell, which is standard on modern Windows
    interpreter = ["powershell", "-Command"]
    
    # This is a single-line PowerShell command.
    # 1. Logs into ECR
    # 2. Builds the image with TWO tags: ":latest" and our unique ":<hash>"
    # 3. Pushes BOTH tags to ECR
    command = "aws ecr get-login-password --region ${data.aws_region.current.name} | docker login --username AWS --password-stdin ${data.aws_caller_identity.current.account_id}.dkr.ecr.${data.aws_region.current.name}.amazonaws.com; docker build --platform linux/amd64 --provenance=false -t ${aws_ecr_repository.agent_lambda_repo.repository_url}:latest -f Lambda/agent.Dockerfile ./Lambda; docker push ${aws_ecr_repository.agent_lambda_repo.repository_url}:latest"
  }
  # --- END WINDOWS FIX ---

  depends_on = [aws_ecr_repository.agent_lambda_repo]
}

# =========================================================
# Lambda Function for Bedrock Agent Executor
# =========================================================
resource "aws_lambda_function" "agent_executor" {
  function_name = "${var.project_name}-agent-executor"
  role          = aws_iam_role.lambda_agent_role.arn
  package_type  = "Image"
  timeout       = 300
  memory_size   = 1024

  image_uri = "${aws_ecr_repository.agent_lambda_repo.repository_url}:latest"
  kms_key_arn = aws_kms_key.agent_encryption.arn

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
      S3_BUCKET                = aws_s3_bucket.rag_documents.bucket
      VECTOR_STORE_PATH        = "vector_store/default"
      AWS_REGION               = data.aws_region.current.name
      SECRETS_ARN              = aws_secretsmanager_secret.bedrock_config.arn
      BEDROCK_AGENT_ID         = aws_bedrockagent_agent.rag_agent.agent_id
      BEDROCK_AGENT_ALIAS_NAME = "production"
      SES_SENDER_EMAIL         = var.ses_sender_email
    }
  }

  tracing_config {
    mode = "Active"
  }

  dead_letter_config {
    target_arn = aws_sqs_queue.lambda_dlq.arn
  }

  depends_on = [
    null_resource.build_and_push_agent_image,
    aws_iam_role.lambda_agent_role,
    aws_cloudwatch_log_group.lambda_agent_logs
  ]

  tags = {
    Name = "${var.project_name}-agent-executor"
  }
}