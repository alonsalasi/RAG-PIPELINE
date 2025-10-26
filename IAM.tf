# -----------------------------------------------------------------
# API Lambda Role (Handles /query, /list-files, /get-upload-url, /delete-file)
# -----------------------------------------------------------------
resource "aws_iam_role" "lambda_api_role" {
  name = "${var.project_name}-lambda-api-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Principal = { Service = "lambda.amazonaws.com" },
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_policy" "lambda_api_policy" {
  name        = "${var.project_name}-lambda-api-policy"
  description = "Permissions for Lambda API: S3, Bedrock, Translate, and Logs."

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      # --- CloudWatch Logs ---
      {
        Effect = "Allow",
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/*:*"
      },

      # --- S3 for processed_chunks (read) ---
      {
        Effect   = "Allow",
        Action   = "s3:ListBucket",
        Resource = aws_s3_bucket.rag_documents.arn,
        Condition = {
          StringLike = { "s3:prefix" = "processed_chunks/*" }
        }
      },
      {
        Effect   = "Allow",
        Action   = ["s3:GetObject"],
        Resource = "${aws_s3_bucket.rag_documents.arn}/processed_chunks/*"
      },

      # --- S3 uploads (write, list, and now delete) ---
      {
        Effect   = "Allow",
        Action   = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject"   # ✅ NEW: allows delete from uploads/
        ],
        Resource = "${aws_s3_bucket.rag_documents.arn}/uploads/*"
      },
      {
        Effect   = "Allow",
        Action   = "s3:ListBucket",
        Resource = aws_s3_bucket.rag_documents.arn,
        Condition = {
          StringLike = { "s3:prefix" = "uploads/*" }
        }
      },

      # --- S3 vector store (read/write/delete) ---
      {
        Effect   = "Allow",
        Action   = ["s3:ListBucket"],
        Resource = aws_s3_bucket.rag_documents.arn,
        Condition = {
          StringLike = { "s3:prefix" = "vector_store/*" }
        }
      },
      {
        Effect   = "Allow",
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
        Resource = "${aws_s3_bucket.rag_documents.arn}/vector_store/*"
      },

      # --- Bedrock (LLM and Embeddings) ---
      {
        Effect = "Allow",
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ],
        Resource = [
          "arn:aws:bedrock:${var.aws_region}::foundation-model/meta.llama3-8b-instruct-v1:0",
          "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.titan-embed-text-v1*"
        ]
      },
      {
        Effect = "Allow",
        Action = [
          "bedrock:GetFoundationModel",
          "bedrock:ListFoundationModels"
        ],
        Resource = "*"
      },

      # --- Translate Permission ---
      {
        Effect   = "Allow",
        Action   = "translate:TranslateText",
        Resource = "*"
      }
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

# -----------------------------------------------------------------
# Ingestion Lambda Role (Triggered by SQS)
# -----------------------------------------------------------------
resource "aws_iam_role" "lambda_ingestion_role" {
  name = "${var.project_name}-lambda-ingest-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Principal = { Service = "lambda.amazonaws.com" },
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_policy" "lambda_ingestion_policy" {
  name        = "${var.project_name}-lambda-ingest-policy"
  description = "Permissions for Ingestion: SQS, S3, Logs, ECR, Bedrock, Translate."

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      # --- CloudWatch Logs ---
      {
        Effect   = "Allow",
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/*:*"
      },
      # --- SQS ---
      {
        Effect   = "Allow",
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"],
        Resource = aws_sqs_queue.rag_ingestion_queue.arn
      },
      # --- S3 (Full bucket access) ---
      {
        Effect = "Allow",
        Action = ["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:DeleteObject"],
        Resource = [
          aws_s3_bucket.rag_documents.arn,
          "${aws_s3_bucket.rag_documents.arn}/*"
        ]
      },
      # --- ECR ---
      {
        Effect = "Allow",
        Action = [
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:BatchCheckLayerAvailability"
        ],
        Resource = aws_ecr_repository.ingestion_lambda_repo.arn
      },

      # --- Bedrock Permission for Embeddings ---
      {
        Effect   = "Allow",
        Action   = ["bedrock:InvokeModel"],
        Resource = "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.titan-embed-text-v1*"
      },

      # --- Translate Permission ---
      {
        Effect   = "Allow",
        Action   = "translate:TranslateText",
        Resource = "*"
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

# -----------------------------------------------------------------
# API Gateway Logging Role
# -----------------------------------------------------------------
resource "aws_iam_role" "apigw_logs_role" {
  name = "${var.project_name}-apigw-logs-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Principal = { Service = "apigateway.amazonaws.com" },
        Action = "sts:AssumeRole"
      }
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
        Effect = "Allow",
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogGroups",
          "logs:DescribeLogStreams"
        ],
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "apigw_logs_attach" {
  role       = aws_iam_role.apigw_logs_role.name
  policy_arn = aws_iam_policy.apigw_logs_policy.arn
}

resource "aws_api_gateway_account" "apigw_account_settings" {
  cloudwatch_role_arn = aws_iam_role.apigw_logs_role.arn
}
