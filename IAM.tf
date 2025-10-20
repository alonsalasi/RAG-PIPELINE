data "aws_caller_identity" "current" {}

resource "aws_iam_role" "ecs_execution_role" {
  name               = "${var.project_name}-ecs-exec-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect    = "Allow",
        Principal = { Service = "ecs-tasks.amazonaws.com" },
        Action    = "sts:AssumeRole"
      },
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution_policy" {
  role       = aws_iam_role.ecs_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "ecs_task_role" {
  name               = "${var.project_name}-ecs-task-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect    = "Allow",
        Principal = { Service = "ecs-tasks.amazonaws.com" },
        Action    = "sts:AssumeRole"
      },
    ]
  })
}

resource "aws_iam_policy" "ecs_common_policy" {
  name        = "${var.project_name}-ecs-common-policy"
  description = "Permissions for ECS tasks to read S3, manage SQS, retrieve RDS secrets, and use Textract."
  
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ],
        Resource = aws_sqs_queue.rag_ingestion_queue.arn
      },
      {
        Effect = "Allow",
        Action = [
          "s3:GetObject"
        ],
        Resource = "${aws_s3_bucket.rag_documents.arn}/*"
      },
      {
        Effect = "Allow",
        Action = [
          "secretsmanager:GetSecretValue"
        ],
        Resource = aws_secretsmanager_secret.rds_master_credentials.arn
      },
      {
        Effect = "Allow",
        Action = [
          "textract:StartDocumentAnalysis",
          "textract:GetDocumentAnalysis",
          "textract:DetectDocumentText",
        ],
        Resource = "*"
      },
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_common_attach" {
  role       = aws_iam_role.ecs_task_role.name
  policy_arn = aws_iam_policy.ecs_common_policy.arn
}

resource "aws_iam_policy" "ecs_bedrock_policy" {
  name        = "${var.project_name}-ecs-bedrock-policy"
  description = "Permissions for RAG application to call AWS Bedrock."
  
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = "bedrock:InvokeModel",
        Resource = "*" 
      },
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_bedrock_attach" {
  role       = aws_iam_role.ecs_task_role.name
  policy_arn = aws_iam_policy.ecs_bedrock_policy.arn
}

resource "aws_iam_policy" "ecs_opensearch_policy" {
  name        = "${var.project_name}-ecs-opensearch-policy"
  description = "Permissions for RAG application to access OpenSearch."
  
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = "es:ESHttp*",
        Resource = "${aws_opensearch_domain.vector_search.arn}/*"
      },
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_opensearch_attach" {
  role       = aws_iam_role.ecs_task_role.name
  policy_arn = aws_iam_policy.ecs_opensearch_policy.arn
}