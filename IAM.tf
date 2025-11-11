###############################################################
# API Gateway → CloudWatch Logs Integration
###############################################################
resource "aws_iam_role" "apigw_cloudwatch_role" {
  name = "${var.project_name}-apigw-cloudwatch-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect    = "Allow",
      Principal = { Service = "apigateway.amazonaws.com" },
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "apigw_cloudwatch_policy" {
  name = "${var.project_name}-apigw-cloudwatch-policy-${var.environment}"
  role = aws_iam_role.apigw_cloudwatch_role.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
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
    }]
  })
}

resource "aws_api_gateway_account" "apigw_account_settings" {
  cloudwatch_role_arn = aws_iam_role.apigw_cloudwatch_role.arn
}

###############################################################
# 1️⃣ INGESTION LAMBDA ROLE
###############################################################
resource "aws_iam_role" "lambda_ingestion_role" {
  name = "${var.project_name}-lambda-ingestion-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect    = "Allow",
      Principal = { Service = "lambda.amazonaws.com" },
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Name = "Lambda Ingestion Role" }
}

resource "aws_iam_policy" "lambda_ingestion_policy" {
  name        = "${var.project_name}-lambda-ingestion-policy-${var.environment}"
  description = "Allows Lambda to access S3, SNS, SQS, Bedrock, Textract, and logs"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
        Resource = [
          "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}-*",
          "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}-*:*"
        ]
      },
      {
        Effect = "Allow",
        Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
        Resource = [aws_s3_bucket.rag_documents.arn, "${aws_s3_bucket.rag_documents.arn}/*"]
      },
      {
        Effect = "Allow",
        Action = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"],
        Resource = [aws_sqs_queue.rag_ingestion_queue.arn]
      },
      {
        Effect = "Allow",
        Action = ["sns:Publish", "sns:Subscribe"],
        Resource = aws_sns_topic.document_upload_topic.arn
      },
      {
        Effect = "Allow",
        Action = ["textract:DetectDocumentText", "textract:AnalyzeDocument"],
        Resource = "*",
        Condition = {
          StringEquals = {
            "aws:RequestedRegion" = data.aws_region.current.name
          }
        }
      },
      {
        Effect = "Allow",
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
          "bedrock:GetFoundationModel",
          "bedrock:ListFoundationModels"
        ],
        Resource = "*",
        Condition = {
          StringEquals = {
            "aws:RequestedRegion" = data.aws_region.current.name
          }
        }
      },
      {
        Effect = "Allow",
        Action = [
          "aws-marketplace:ViewSubscriptions",
          "aws-marketplace:Subscribe",
          "aws-marketplace:Unsubscribe"
        ],
        Resource = "*"
      },
      {
        Effect = "Allow",
        Action = ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey"],
        Resource = [
          aws_kms_key.agent_encryption.arn,
          "arn:aws:kms:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:key/*"
        ]
      },
      {
        Effect = "Allow",
        Action = ["secretsmanager:GetSecretValue"],
        Resource = [
          aws_secretsmanager_secret.bedrock_config.arn
        ]
      },
      {
        Effect = "Allow",
        Action = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"],
        Resource = "*",
        Condition = {
          StringEquals = {
            "aws:RequestedRegion" = data.aws_region.current.name
          }
        }
      },
      {
        Effect = "Allow",
        Action = ["sqs:SendMessage"],
        Resource = [
          aws_sqs_queue.rag_ingestion_queue.arn,
          "${aws_sqs_queue.rag_ingestion_queue.arn}-dlq"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_ingestion_policy_attach" {
  role       = aws_iam_role.lambda_ingestion_role.name
  policy_arn = aws_iam_policy.lambda_ingestion_policy.arn
}

resource "aws_iam_role_policy_attachment" "lambda_ingestion_basic_attach" {
  role       = aws_iam_role.lambda_ingestion_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "lambda_ingestion_vpc_attach" {
  role       = aws_iam_role.lambda_ingestion_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

###############################################################
# 2️⃣ AGENT LAMBDA ROLE  (Fix: proper alias-scoped Bedrock access)
###############################################################
resource "aws_iam_role" "lambda_agent_role" {
  name = "${var.project_name}-lambda-agent-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect    = "Allow",
      Principal = { Service = "lambda.amazonaws.com" },
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Name = "${var.project_name}-lambda-agent-role" }
}

resource "aws_iam_policy" "lambda_agent_policy" {
  name        = "${var.project_name}-lambda-agent-policy-${var.environment}"
  description = "Policy for Agent Lambda to access Bedrock Agents, S3, and models"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      # Logs
      {
        Effect = "Allow",
        Action = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents", "logs:FilterLogEvents"],
        Resource = "arn:aws:logs:*:*:*"
      },

      # S3
      {
        Effect = "Allow",
        Action = ["s3:GetObject", "s3:ListBucket", "s3:PutObject", "s3:DeleteObject"],
        Resource = [aws_s3_bucket.rag_documents.arn, "${aws_s3_bucket.rag_documents.arn}/*"]
      },

      # Bedrock Agent invocation (runtime + control plane)
      {
        Effect = "Allow",
        Action = [
          "bedrock-agent-runtime:InvokeAgent",
          "bedrock-agent-runtime:Retrieve",
          "bedrock-agent-runtime:RetrieveAndGenerate",
          "bedrock:InvokeAgent"
        ],
        Resource = "*"
      },

      {
        Effect = "Allow",
        Action = ["bedrock:ListAgentAliases"],
        Resource = "*"
      },

      # Foundation models
      {
        Effect = "Allow",
        Action = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
        Resource = "*"
      },
      # KMS for encryption
      {
        Effect = "Allow",
        Action = ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey"],
        Resource = "*"
      },
      # Secrets Manager
      {
        Effect = "Allow",
        Action = ["secretsmanager:GetSecretValue"],
        Resource = "*"
      },
      # X-Ray tracing
      {
        Effect = "Allow",
        Action = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"],
        Resource = "*"
      },
      # DLQ access
      {
        Effect = "Allow",
        Action = ["sqs:SendMessage"],
        Resource = "*"
      },
      # Self-invoke for async operations
      {
        Effect = "Allow",
        Action = ["lambda:InvokeFunction"],
        Resource = "arn:aws:lambda:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:function:${var.project_name}-agent-executor"
      },
      # SES email sending - DISABLED (requires NAT Gateway)
      # {
      #   Effect = "Allow",
      #   Action = ["ses:SendEmail", "ses:SendRawEmail"],
      #   Resource = "*"
      # }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_agent_policy_attachment" {
  role       = aws_iam_role.lambda_agent_role.name
  policy_arn = aws_iam_policy.lambda_agent_policy.arn
}

resource "aws_iam_role_policy_attachment" "lambda_agent_basic_execution_attach" {
  role       = aws_iam_role.lambda_agent_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "lambda_agent_vpc_attach" {
  role       = aws_iam_role.lambda_agent_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

###############################################################
# 3️⃣ BEDROCK AGENT ROLE (Fix: dynamic Lambda ARN + permission)
###############################################################
resource "aws_iam_role" "bedrock_agent_role" {
  name = "${var.project_name}-bedrock-agent-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Action    = "sts:AssumeRole",
      Effect    = "Allow",
      Principal = { Service = "bedrock.amazonaws.com" }
    }]
  })

  tags = { Name = "${var.project_name}-bedrock-agent-role" }
}

resource "aws_iam_policy" "bedrock_agent_policy" {
  name        = "${var.project_name}-bedrock-agent-policy-${var.environment}"
  description = "Policy for Bedrock Agent to invoke Lambda, access S3, and call models"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      # Allow Bedrock Agent to invoke the Action Group Lambda
      {
        Effect = "Allow",
        Action = ["lambda:InvokeFunction"],
        Resource = [
          aws_lambda_function.agent_executor.arn,
          "${aws_lambda_function.agent_executor.arn}:*"
        ]
      },

      # S3 access for RAG document bucket
      {
        Effect = "Allow",
        Action = ["s3:GetObject", "s3:ListBucket", "s3:PutObject"],
        Resource = [aws_s3_bucket.rag_documents.arn, "${aws_s3_bucket.rag_documents.arn}/*"]
      },

      # Foundation model access
      {
        Effect = "Allow",
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
          "bedrock:GetFoundationModel",
          "bedrock:ListFoundationModels",
          "bedrock:GetInferenceProfile",
          "bedrock:ListInferenceProfiles"
        ],
        Resource = "*"
      },
      
      # Guardrail access
      {
        Effect = "Allow",
        Action = [
          "bedrock:ApplyGuardrail",
          "bedrock:GetGuardrail"
        ],
        Resource = "*"
      },
      
      # AWS Marketplace access for model subscriptions
      {
        Effect = "Allow",
        Action = [
          "aws-marketplace:ViewSubscriptions"
        ],
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "bedrock_agent_policy_attach" {
  role       = aws_iam_role.bedrock_agent_role.name
  policy_arn = aws_iam_policy.bedrock_agent_policy.arn
}

###############################################################
# 4️⃣ Lambda permission: allow Bedrock service to invoke it
###############################################################
resource "aws_lambda_permission" "allow_bedrock_invoke" {
  statement_id  = "AllowBedrockInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.agent_executor.function_name
  principal     = "bedrock.amazonaws.com"
  source_arn    = "arn:aws:bedrock:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:agent/*"
}

#########################
# 4️⃣ Cognito Permissions
#########################

resource "aws_iam_role" "cognito_sms_role" {
  name = "${var.project_name}-cognito-sms-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "cognito-idp.amazonaws.com"
      }
      Action = "sts:AssumeRole"
      Condition = {
        StringEquals = {
          "sts:ExternalId" = "${var.project_name}-cognito-sms"
        }
      }
    }]
  })

  tags = {
    Name = "${var.project_name}-cognito-sms-role"
    Environment = var.environment
  }
}

resource "aws_iam_role_policy" "cognito_sms_policy" {
  name = "${var.project_name}-cognito-sms-policy-${var.environment}"
  role = aws_iam_role.cognito_sms_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "sns:Publish"
      ]
      Resource = "arn:aws:sns:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:*"
      Condition = {
        StringEquals = {
          "sns:Protocol" = "sms"
        }
      }
    }]
  })
}
