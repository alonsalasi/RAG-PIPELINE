resource "aws_iam_role" "lambda_api_role" {
  name = "${var.project_name}-lambda-api-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect    = "Allow",
        Principal = { Service = "lambda.amazonaws.com" },
        Action    = "sts:AssumeRole"
      },
    ]
  })
}

resource "aws_iam_policy" "lambda_api_policy" {
  name        = "${var.project_name}-lambda-api-policy"
  description = "Permissions for Lambda API to read S3 chunks, call Bedrock, generate presigned URLs, and log."
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect   = "Allow",
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/*:*"
      },
      {
        Effect  = "Allow",
        Action  = "s3:ListBucket",
        Resource = aws_s3_bucket.rag_documents.arn,
        Condition = {
          StringLike = {
            "s3:prefix" = "processed_chunks/*"
          }
        }
      },
      {
        Effect = "Allow",
        Action = [
          "s3:GetObject"
        ],
        Resource = "${aws_s3_bucket.rag_documents.arn}/processed_chunks/*"
      },
      {
        Effect = "Allow",
        Action = [
          "s3:PutObject"
        ],
        Resource = "${aws_s3_bucket.rag_documents.arn}/incoming/*"
      },
      {
        Effect   = "Allow",
        Action   = "bedrock:InvokeModel",
        Resource = "*"
      },
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_api_policy_attach" {
  role       = aws_iam_role.lambda_api_role.name
  policy_arn = aws_iam_policy.lambda_api_policy.arn
}

resource "aws_iam_role_policy_attachment" "lambda_api_vpc_attach" {
  role       = aws_iam_role.lambda_api_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# --- NEW: Role and Policy for API Gateway to write to CloudWatch ---
resource "aws_iam_role" "apigw_logs_role" {
  name = "${var.project_name}-apigw-logs-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect    = "Allow",
        Principal = { Service = "apigateway.amazonaws.com" },
        Action    = "sts:AssumeRole"
      },
    ]
  })
}

resource "aws_iam_policy" "apigw_logs_policy" {
  name        = "${var.project_name}-apigw-logs-policy"
  description = "Allows API Gateway to write execution logs to CloudWatch."
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect   = "Allow",
        Action   = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        Resource = "*" # Must be '*' for creating the initial log group
      },
    ]
  })
}

resource "aws_iam_role_policy_attachment" "apigw_logs_attach" {
  role       = aws_iam_role.apigw_logs_role.name
  policy_arn = aws_iam_policy.apigw_logs_policy.arn
}

resource "aws_api_gateway_account" "apigw_account_settings" {
  cloudwatch_role_arn = aws_iam_role.apigw_logs_role.arn
  depends_on          = [aws_iam_role_policy_attachment.apigw_logs_attach]
}
# --- END NEW API GATEWAY LOGGING ROLE ---


resource "aws_iam_role" "lambda_ingestion_role" {
  name = "${var.project_name}-lambda-ingest-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect    = "Allow",
        Principal = { Service = "lambda.amazonaws.com" },
        Action    = "sts:AssumeRole"
      },
    ]
  })
}

resource "aws_iam_policy" "lambda_ingestion_policy" {
  name        = "${var.project_name}-lambda-ingest-policy"
  description = "Permissions for Ingestion Lambda: SQS, S3, Logs, ECR."
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect   = "Allow",
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/*:*"
      },
      {
        Effect   = "Allow",
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"],
        Resource = aws_sqs_queue.rag_ingestion_queue.arn
      },
      {
        Effect   = "Allow",
        Action   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:DeleteObject"],
        Resource = [
          aws_s3_bucket.rag_documents.arn,
          "${aws_s3_bucket.rag_documents.arn}/*"
        ]
      },
      {
        Effect = "Allow",
        Action = [
            "ecr:GetDownloadUrlForLayer",
            "ecr:BatchGetImage",
            "ecr:BatchCheckLayerAvailability"
        ],
        Resource = aws_ecr_repository.ingestion_lambda_repo.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_ingestion_attach" {
  role       = aws_iam_role.lambda_ingestion_role.name
  policy_arn = aws_iam_policy.lambda_ingestion_policy.arn
}

resource "aws_iam_role_policy_attachment" "lambda_ingestion_vpc_attach" {
  role       = aws_iam_role.lambda_ingestion_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}