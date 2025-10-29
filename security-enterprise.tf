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
  policy_arn = "arn:aws:iam::aws:policy/service-role/ConfigRole"
}

resource "aws_iam_role_policy" "config_s3_policy" {
  name = "${var.project_name}-config-s3-policy"
  role = aws_iam_role.config_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["s3:PutObject", "s3:GetBucketAcl"]
      Resource = [
        aws_s3_bucket.config_logs.arn,
        "${aws_s3_bucket.config_logs.arn}/*"
      ]
    }]
  })
}

# =========================================================
# GuardDuty - Threat Detection
# =========================================================
resource "aws_guardduty_detector" "main" {
  enable = true
  finding_publishing_frequency = "FIFTEEN_MINUTES"

  datasources {
    s3_logs {
      enable = true
    }
    kubernetes {
      audit_logs {
        enable = false
      }
    }
    malware_protection {
      scan_ec2_instance_with_findings {
        ebs_volumes {
          enable = true
        }
      }
    }
  }

  tags = {
    Name = "${var.project_name}-guardduty"
  }
}

# =========================================================
# Secrets Manager for Sensitive Configuration
# =========================================================
resource "aws_secretsmanager_secret" "bedrock_config" {
  name                    = "${var.project_name}-bedrock-config"
  description             = "Bedrock Agent configuration"
  kms_key_id              = aws_kms_key.agent_encryption.arn
  recovery_window_in_days = 7

  tags = {
    Name = "${var.project_name}-bedrock-config"
  }
}

resource "aws_secretsmanager_secret_version" "bedrock_config" {
  secret_id = aws_secretsmanager_secret.bedrock_config.id
  secret_string = jsonencode({
    agent_id    = aws_bedrockagent_agent.rag_agent.agent_id
    agent_alias = "production"
    model_id    = "amazon.titan-embed-text-v1"
  })
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
# S3 Backup Bucket with Cross-Region Replication
# =========================================================
resource "aws_s3_bucket" "rag_documents_backup" {
  bucket = "${var.project_name}-rag-documents-backup-${data.aws_caller_identity.current.account_id}"
  tags = {
    Name = "${var.project_name}-rag-documents-backup"
  }
}

resource "aws_s3_bucket_versioning" "rag_documents_backup_versioning" {
  bucket = aws_s3_bucket.rag_documents_backup.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "rag_documents_backup_encryption" {
  bucket = aws_s3_bucket.rag_documents_backup.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.agent_encryption.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "rag_documents_backup_block" {
  bucket                  = aws_s3_bucket.rag_documents_backup.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
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
}

resource "aws_cloudwatch_metric_alarm" "waf_blocked_requests" {
  alarm_name          = "${var.project_name}-waf-blocked-requests"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "BlockedRequests"
  namespace           = "AWS/WAFV2"
  period              = 300
  statistic           = "Sum"
  threshold           = 100
  alarm_description   = "High number of WAF blocked requests"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.security_alerts.arn]

  dimensions = {
    WebACL = aws_wafv2_web_acl.api_protection.name
    Region = data.aws_region.current.name
    Rule   = "ALL"
  }
}
