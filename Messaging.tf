resource "aws_sqs_queue" "rag_ingestion_queue" {
  name                       = "${var.project_name}-ingestion-queue-${var.environment}"
  delay_seconds              = 0
  max_message_size           = 262144
  message_retention_seconds  = 345600
  # Set visibility timeout high to match Lambda max timeout (15 mins)
  visibility_timeout_seconds = 900 
  
  tags = {
    Name = "RAG Ingestion Queue"
  }
}

resource "aws_sns_topic" "document_upload_topic" {
  name = "${var.project_name}-document-upload-topic-${var.environment}"
  tags = {
    Name = "RAG Document Upload Topic"
  }
}

# --- 1. Policy: Allows SNS to push messages into the SQS Queue ---
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

# --- 2. CRITICAL FIX: Policy to allow S3 to PUBLISH to the SNS Topic ---
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

# --- 3. Subscription: Links the SQS Queue to the SNS Topic ---
resource "aws_sns_topic_subscription" "sqs_to_sns_subscription" {
  topic_arn            = aws_sns_topic.document_upload_topic.arn
  protocol             = "sqs"
  endpoint             = aws_sqs_queue.rag_ingestion_queue.arn
  raw_message_delivery = true 
}

# --- 4. S3 Notification: Triggers SNS when file is uploaded ---
resource "aws_s3_bucket_notification" "s3_to_sns" {
  # Referencing the S3 bucket resource defined in s3.tf
  bucket = aws_s3_bucket.rag_documents.id 

  topic {
    id        = "document_uploaded_notification"
    topic_arn = aws_sns_topic.document_upload_topic.arn
    events    = ["s3:ObjectCreated:*"]
    # Only notify for new objects in the 'incoming/' prefix
    filter_prefix = "incoming/" 
  }
  
  # Dependency on the SNS policy and SQS subscription
  depends_on = [
    aws_sns_topic_subscription.sqs_to_sns_subscription,
    aws_sns_topic_policy.sns_allow_s3_publish
  ]
}

# --- 5. CRITICAL: Lambda Event Source Mapping (The SQS Trigger) ---
# This resource links the SQS queue to the Ingestion Lambda function.
resource "aws_lambda_event_source_mapping" "ingestion_worker_trigger" {
  event_source_arn  = aws_sqs_queue.rag_ingestion_queue.arn
  function_name     = aws_lambda_function.ingestion_worker.function_name
  batch_size        = 1 
  enabled           = true
}
