resource "aws_lambda_function" "ingestion_worker" {
  function_name = "${var.project_name}-ingestion-worker"
  description   = "Version: ${var.ingestion_version}"
  role          = aws_iam_role.lambda_ingestion_role.arn
  timeout       = 900
  memory_size   = 2048

  package_type = "Image"
  image_uri    = "${aws_ecr_repository.ingestion_lambda_repo.repository_url}:${var.ingestion_image_tag}"

  vpc_config {
    subnet_ids         = aws_subnet.private.*.id
    security_group_ids = [aws_security_group.lambda_sg.id]
  }

  environment {
    variables = {
      S3_BUCKET  = aws_s3_bucket.rag_documents.bucket
    }
  }

  depends_on = [aws_ecr_repository.ingestion_lambda_repo]
}