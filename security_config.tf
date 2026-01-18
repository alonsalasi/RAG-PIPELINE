# Enterprise Security Hardening

# =========================================================
# AWS Config - Compliance Monitoring
# =========================================================
resource "aws_config_configuration_recorder" "main" {
  name     = "${var.project_name}-config-recorder"
  role_arn = aws_iam_role.config_role.arn

  recording_group {
    all_supported                 = true
    include_global_resource_types = true
  }
}

resource "aws_config_delivery_channel" "main" {
  name           = "${var.project_name}-config-delivery"
  s3_bucket_name = aws_s3_bucket.config_logs.bucket
  depends_on     = [aws_config_configuration_recorder.main]

  lifecycle {
    create_before_destroy = true
    prevent_destroy       = false
  }
}

resource "aws_config_configuration_recorder_status" "main" {
  name       = aws_config_configuration_recorder.main.name
  is_enabled = true
  depends_on = [aws_config_delivery_channel.main]
}

resource "aws_s3_bucket" "config_logs" {
  bucket = "${var.project_name}-config-logs-${data.aws_caller_identity.current.account_id}"
  tags = {
    Name = "${var.project_name}-config-logs"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "config_logs_encryption" {
  bucket = aws_s3_bucket.config_logs.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.agent_encryption.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "config_logs_block" {
  bucket                  = aws_s3_bucket.config_logs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_iam_role" "config_role" {
  name = "${var.project_name}-config-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = { Service = "config.amazonaws.com" }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "config_policy" {
  role       = aws_iam_role.config_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWS_ConfigRole"
}

resource "aws_iam_role_policy" "config_s3_policy" {
  name = "${var.project_name}-config-s3-policy"
  role = aws_iam_role.config_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["s3:PutObject", "s3:GetBucketAcl"]
        Resource = [
          aws_s3_bucket.config_logs.arn,
          "${aws_s3_bucket.config_logs.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetBucketEncryption",
          "lambda:GetFunctionConfiguration",
          "lambda:GetPolicy",
          "ec2:DescribeVpcs",
          "ec2:DescribeInternetGateways"
        ]
        Resource = "*"
      }
    ]
  })
}

# =========================================================
# AWS Config Rules - Security Compliance
# =========================================================
resource "aws_sns_topic" "config_alerts" {
  name = "${var.project_name}-config-alerts"
  kms_master_key_id = aws_kms_key.agent_encryption.arn
}

# Rule: S3 bucket encryption must be enabled
resource "aws_config_config_rule" "s3_bucket_encryption" {
  name = "${var.project_name}-s3-encryption-required"

  source {
    owner             = "AWS"
    source_identifier = "S3_BUCKET_SERVER_SIDE_ENCRYPTION_ENABLED"
  }

  depends_on = [aws_config_configuration_recorder.main]
}

# Rule: Lambda functions must not have public access
resource "aws_config_config_rule" "lambda_no_public_access" {
  name = "${var.project_name}-lambda-no-public-access"

  source {
    owner             = "AWS"
    source_identifier = "LAMBDA_FUNCTION_PUBLIC_ACCESS_PROHIBITED"
  }

  depends_on = [aws_config_configuration_recorder.main]
}

# Rule: Lambda must be in VPC (no direct internet access)
resource "aws_config_config_rule" "lambda_inside_vpc" {
  name = "${var.project_name}-lambda-inside-vpc"

  source {
    owner             = "AWS"
    source_identifier = "LAMBDA_INSIDE_VPC"
  }

  depends_on = [aws_config_configuration_recorder.main]
}

# EventBridge rule to capture Config compliance changes
resource "aws_cloudwatch_event_rule" "config_compliance_change" {
  name        = "${var.project_name}-config-compliance-change"
  description = "Capture Config compliance state changes"

  event_pattern = jsonencode({
    source      = ["aws.config"]
    detail-type = ["Config Rules Compliance Change"]
    detail = {
      configRuleName = [
        aws_config_config_rule.s3_bucket_encryption.name,
        aws_config_config_rule.lambda_no_public_access.name,
        aws_config_config_rule.lambda_inside_vpc.name
      ]
      newEvaluationResult = {
        complianceType = ["NON_COMPLIANT"]
      }
    }
  })
}

resource "aws_cloudwatch_event_target" "config_to_sns" {
  rule      = aws_cloudwatch_event_rule.config_compliance_change.name
  target_id = "SendToSNS"
  arn       = aws_sns_topic.config_alerts.arn

  input_transformer {
    input_paths = {
      rule     = "$.detail.configRuleName"
      resource = "$.detail.resourceId"
      type     = "$.detail.resourceType"
    }
    input_template = "\"SECURITY ALERT: Config rule <rule> detected non-compliance.\\nResource: <resource>\\nType: <type>\\nAction Required: Investigate immediately.\""
  }
}

resource "aws_sns_topic_policy" "config_alerts_policy" {
  arn = aws_sns_topic.config_alerts.arn

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "events.amazonaws.com"
      }
      Action   = "SNS:Publish"
      Resource = aws_sns_topic.config_alerts.arn
    }]
  })
}

# =========================================================
# GuardDuty - Threat Detection
# =========================================================
resource "aws_guardduty_detector" "main" {
  enable = true
  finding_publishing_frequency = "FIFTEEN_MINUTES"

  tags = {
    Name = "${var.project_name}-guardduty"
  }
}

# GuardDuty Features - S3 Protection
resource "aws_guardduty_detector_feature" "s3_protection" {
  detector_id = aws_guardduty_detector.main.id
  name        = "S3_DATA_EVENTS"
  status      = "ENABLED"
}

# GuardDuty Features - EBS Malware Protection
resource "aws_guardduty_detector_feature" "ebs_malware_protection" {
  detector_id = aws_guardduty_detector.main.id
  name        = "EBS_MALWARE_PROTECTION"
  status      = "ENABLED"
}

# =========================================================
# CloudWatch Log Groups with Proper Retention
# =========================================================
resource "aws_cloudwatch_log_group" "lambda_ingestion_logs" {
  name              = "/aws/lambda/${aws_lambda_function.ingestion_worker.function_name}"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.agent_encryption.arn

  tags = {
    Name = "${var.project_name}-ingestion-logs"
  }
}

resource "aws_cloudwatch_log_group" "lambda_agent_logs" {
  name              = "/aws/lambda/${aws_lambda_function.agent_executor.function_name}"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.agent_encryption.arn

  tags = {
    Name = "${var.project_name}-agent-logs"
  }
}

# =========================================================
# CloudWatch Alarms for Security Monitoring
# =========================================================
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "${var.project_name}-lambda-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 10
  alarm_description   = "Lambda error rate too high"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.security_alerts.arn]

  dimensions = {
    FunctionName = aws_lambda_function.agent_executor.function_name
  }
}

resource "aws_cloudwatch_metric_alarm" "api_4xx_errors" {
  alarm_name          = "${var.project_name}-api-4xx-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "4XXError"
  namespace           = "AWS/ApiGateway"
  period              = 300
  statistic           = "Sum"
  threshold           = 50
  alarm_description   = "API Gateway 4xx error rate too high"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.security_alerts.arn]

  dimensions = {
    ApiId = aws_apigatewayv2_api.rag_api_gateway.id
  }

  lifecycle {
    create_before_destroy = true
  }
}

# WAF alarm removed - WAF not compatible with API Gateway v2
