resource "aws_sqs_queue" "ingestion_queue" {
  name                       = "${var.project_name}-ingestion-queue-${var.environment}"
  delay_seconds              = 0
  max_message_size           = 262144
  message_retention_seconds  = 345600
  visibility_timeout_seconds = 300
  
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

data "aws_iam_policy_document" "sqs_allow_sns_publish" {
  statement {
    effect  = "Allow"
    principals {
      type        = "Service"
      identifiers = ["sns.amazonaws.com"]
    }
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.ingestion_queue.arn]
    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_sns_topic.document_upload_topic.arn]
    }
  }
}

resource "aws_sqs_queue_policy" "ingestion_queue_policy" {
  queue_url = aws_sqs_queue.ingestion_queue.id
  policy    = data.aws_iam_policy_document.sqs_allow_sns_publish.json
}

resource "aws_sns_topic_subscription" "sqs_to_sns_subscription" {
  topic_arn = aws_sns_topic.document_upload_topic.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.ingestion_queue.arn
  raw_message_delivery = true 
}

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
  
  # Ensure S3 has permission to publish to the SNS Topic (relies on subscription being ready)
  depends_on = [aws_sns_topic_subscription.sqs_to_sns_subscription]
}
