# =========================================================
# SQS Queues
# =========================================================

# Ingestion Queue
resource "aws_sqs_queue" "rag_ingestion_queue" {
  name                       = "${var.project_name}-ingestion-queue"
  visibility_timeout_seconds = 300
  message_retention_seconds  = 1209600
  receive_wait_time_seconds  = 20
  kms_master_key_id          = aws_kms_key.agent_encryption.arn

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.ingestion_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Name = "${var.project_name}-ingestion-queue"
  }
}

# Ingestion Dead Letter Queue
resource "aws_sqs_queue" "ingestion_dlq" {
  name                      = "${var.project_name}-ingestion-dlq"
  message_retention_seconds = 1209600
  kms_master_key_id         = aws_kms_key.agent_encryption.arn

  tags = {
    Name = "${var.project_name}-ingestion-dlq"
  }
}

# SQS Policy to allow S3 to send messages
resource "aws_sqs_queue_policy" "allow_s3_to_sqs" {
  queue_url = aws_sqs_queue.rag_ingestion_queue.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "s3.amazonaws.com"
        }
        Action   = "sqs:SendMessage"
        Resource = aws_sqs_queue.rag_ingestion_queue.arn
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = aws_s3_bucket.rag_documents.arn
          }
        }
      }
    ]
  })
}

# Agent Dead Letter Queue
resource "aws_sqs_queue" "agent_dlq" {
  name                      = "${var.project_name}-agent-dlq"
  message_retention_seconds = 1209600
  kms_master_key_id         = aws_kms_key.agent_encryption.arn

  tags = {
    Name = "${var.project_name}-agent-dlq"
  }
}

# =========================================================
# SNS Topics
# =========================================================

# Document Upload Topic
resource "aws_sns_topic" "document_upload_topic" {
  name              = "${var.project_name}-document-upload"
  kms_master_key_id = aws_kms_key.agent_encryption.arn

  tags = {
    Name = "${var.project_name}-document-upload"
  }
}

# Security Alerts Topic
resource "aws_sns_topic" "security_alerts" {
  name              = "${var.project_name}-security-alerts"
  kms_master_key_id = aws_kms_key.agent_encryption.arn

  tags = {
    Name = "${var.project_name}-security-alerts"
  }
}

# SNS Email Subscription (conditional)
resource "aws_sns_topic_subscription" "security_alerts_email" {
  count     = var.alert_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.security_alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}
