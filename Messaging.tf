###############################################################
# MESSAGING PIPELINE
# S3 → SNS → SQS → Lambda (Ingestion Worker)
###############################################################

# --- 1. SQS Queue ---
resource "aws_sqs_queue" "rag_ingestion_queue" {
  name                       = "${var.project_name}-ingestion-queue-${var.environment}"
  delay_seconds              = 0
  max_message_size           = 262144
  message_retention_seconds  = 345600
  visibility_timeout_seconds = 900  # Match ingestion lambda timeout

  tags = {
    Name = "RAG Ingestion Queue"
  }
}

# --- 2. SNS Topic ---
resource "aws_sns_topic" "document_upload_topic" {
  name = "${var.project_name}-document-upload-topic-${var.environment}"

  tags = {
    Name = "RAG Document Upload Topic"
  }
}

# --- 3. Allow SNS → SQS publish ---
data "aws_iam_policy_document" "sqs_allow_sns_publish" {
  statement {
    effect    = "Allow"
    principals {
      type        = "Service"
      identifiers = ["sns.amazonaws.com"]
    }
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.rag_ingestion_queue.arn]
    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_sns_topic.document_upload_topic.arn]
    }
  }
}

resource "aws_sqs_queue_policy" "ingestion_queue_policy" {
  queue_url = aws_sqs_queue.rag_ingestion_queue.id
  policy    = data.aws_iam_policy_document.sqs_allow_sns_publish.json
}

# --- 4. Allow S3 → SNS publish ---
resource "aws_sns_topic_policy" "sns_allow_s3_publish" {
  arn = aws_sns_topic.document_upload_topic.arn
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect    = "Allow",
        Principal = { Service = "s3.amazonaws.com" },
        Action    = "sns:Publish",
        Resource  = aws_sns_topic.document_upload_topic.arn,
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = aws_s3_bucket.rag_documents.arn
          }
        }
      }
    ]
  })
}

# --- 5. SNS → SQS subscription ---
resource "aws_sns_topic_subscription" "sqs_to_sns_subscription" {
  topic_arn            = aws_sns_topic.document_upload_topic.arn
  protocol             = "sqs"
  endpoint             = aws_sqs_queue.rag_ingestion_queue.arn
  raw_message_delivery = true
}

# --- 6. S3 → SNS notification ---
resource "aws_s3_bucket_notification" "s3_to_sns" {
  bucket = aws_s3_bucket.rag_documents.id

  topic {
    id        = "document_uploaded_notification"
    topic_arn = aws_sns_topic.document_upload_topic.arn
    events    = ["s3:ObjectCreated:*"]
    # ✅ FIX: Match prefix used in API uploads
    filter_prefix = "uploads/"
  }

  depends_on = [
    aws_sns_topic_subscription.sqs_to_sns_subscription,
    aws_sns_topic_policy.sns_allow_s3_publish
  ]
}

# --- 7. SQS → Lambda trigger ---
resource "aws_lambda_event_source_mapping" "ingestion_worker_trigger" {
  event_source_arn  = aws_sqs_queue.rag_ingestion_queue.arn
  function_name     = aws_lambda_function.ingestion_worker.function_name
  batch_size        = 1
  enabled           = true
}
