###############################################################
# IAM ROLES & POLICIES
###############################################################

###############################################################
# API Gateway → CloudWatch Logs Integration
###############################################################

# Role for API Gateway to write logs to CloudWatch
resource "aws_iam_role" "apigw_cloudwatch_role" {
  name = "${var.project_name}-apigw-cloudwatch-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Principal = {
          Service = "apigateway.amazonaws.com"
        },
        Action = "sts:AssumeRole"
      }
    ]
  })
}

# Inline policy giving API Gateway access to CloudWatch Logs
resource "aws_iam_role_policy" "apigw_cloudwatch_policy" {
  name = "${var.project_name}-apigw-cloudwatch-policy-${var.environment}"
  role = aws_iam_role.apigw_cloudwatch_role.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:DescribeLogGroups",
          "logs:DescribeLogStreams",
          "logs:PutLogEvents",
          "logs:GetLogEvents",
          "logs:FilterLogEvents"
        ],
        Resource = "*"
      }
    ]
  })
}

# API Gateway account — links API Gateway to the above role
resource "aws_api_gateway_account" "apigw_account_settings" {
  cloudwatch_role_arn = aws_iam_role.apigw_cloudwatch_role.arn
}



###########################
# 1️⃣ INGESTION LAMBDA ROLE
###########################
resource "aws_iam_role" "lambda_ingestion_role" {
  name = "${var.project_name}-lambda-ingestion-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Principal = {
          Service = "lambda.amazonaws.com"
        },
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Name = "Lambda Ingestion Role"
  }
}

resource "aws_iam_policy" "lambda_ingestion_policy" {
  name        = "${var.project_name}-lambda-ingestion-policy-${var.environment}"
  description = "Allows Lambda to access S3, SNS, SQS, Bedrock, Textract, and logs"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      # ✅ CloudWatch Logs
      {
        Effect = "Allow",
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        Resource = "arn:aws:logs:*:*:*"
      },

      # ✅ S3 access for uploads, vector store, processed JSON
      {
        Effect = "Allow",
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ],
        Resource = [
          "${aws_s3_bucket.rag_documents.arn}",
          "${aws_s3_bucket.rag_documents.arn}/*"
        ]
      },

      # ✅ SQS permissions
      {
        Effect = "Allow",
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ],
        Resource = [
          aws_sqs_queue.rag_ingestion_queue.arn
        ]
      },

      # ✅ SNS publish + subscribe
      {
        Effect = "Allow",
        Action = [
          "sns:Publish",
          "sns:Subscribe"
        ],
        Resource = aws_sns_topic.document_upload_topic.arn
      },

      # ✅ Textract fallback
      {
        Effect = "Allow",
        Action = [
          "textract:DetectDocumentText",
          "textract:AnalyzeDocument"
        ],
        Resource = "*"
      },

      # ✅ Bedrock access for embeddings
      {
        Effect = "Allow",
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ],
        # FIX: use data.aws_region.current instead of var.region
        Resource = "arn:aws:bedrock:${data.aws_region.current.name}::foundation-model/amazon.titan-*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_ingestion_policy_attach" {
  role       = aws_iam_role.lambda_ingestion_role.name
  policy_arn = aws_iam_policy.lambda_ingestion_policy.arn
}

resource "aws_iam_role_policy_attachment" "lambda_basic_execution_attach" {
  role       = aws_iam_role.lambda_ingestion_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Required for dynamic region substitution
data "aws_region" "current" {}



###########################
# 2️⃣ API LAMBDA ROLE
###########################
resource "aws_iam_role" "lambda_api_role" {
  name = "${var.project_name}-lambda-api-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Principal = {
          Service = "lambda.amazonaws.com"
        },
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Name = "Lambda API Role"
  }
}

resource "aws_iam_policy" "lambda_api_policy" {
  name        = "${var.project_name}-lambda-api-policy-${var.environment}"
  description = "Allows API Lambda to query Bedrock, list S3 files, and log events."

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      # ✅ CloudWatch Logs
      {
        Effect = "Allow",
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        Resource = "arn:aws:logs:*:*:*"
      },

      # ✅ S3 access (list + get processed files)
      {
        Effect = "Allow",
        Action = [
          "s3:GetObject",
          "s3:ListBucket",
          "s3:DeleteObject",
          "s3:PutObject"
        ],
        Resource = [
          "${aws_s3_bucket.rag_documents.arn}",
          "${aws_s3_bucket.rag_documents.arn}/*"
        ]
      },

      # ✅ Bedrock model access
      {
        Effect = "Allow",
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ],
        Resource = "arn:aws:bedrock:${data.aws_region.current.name}::foundation-model/amazon.titan-*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_api_policy_attach" {
  role       = aws_iam_role.lambda_api_role.name
  policy_arn = aws_iam_policy.lambda_api_policy.arn
}

resource "aws_iam_role_policy_attachment" "lambda_api_basic_execution_attach" {
  role       = aws_iam_role.lambda_api_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}


