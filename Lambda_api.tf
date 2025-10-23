resource "aws_s3_object" "api_lambda_zip" {
  bucket = aws_s3_bucket.rag_documents.id
  key    = "lambda_zips/api_query_service.zip"
  source = "lambda_api_deployment_package.zip"
}

resource "aws_lambda_function" "api_query_service" {
  function_name = "${var.project_name}-api-query-service"
  description   = "Version: ${var.api_version}"
  role          = aws_iam_role.lambda_api_role.arn
  handler       = "lambda_api_handler.lambda_handler"
  runtime       = "python3.11"
  timeout       = 90
  memory_size   = 512

  s3_bucket = aws_s3_object.api_lambda_zip.bucket
  s3_key    = aws_s3_object.api_lambda_zip.key

  source_code_hash = aws_s3_object.api_lambda_zip.source_hash

  vpc_config {
    subnet_ids         = aws_subnet.private.*.id
security_group_ids = [aws_security_group.lambda_sg.id]
  }

  environment {
    variables = {
      S3_DOCUMENTS_BUCKET = aws_s3_bucket.rag_documents.bucket
    }
  }
}