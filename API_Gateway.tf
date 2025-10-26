resource "aws_apigatewayv2_api" "rag_api_gateway" {
  name          = "${var.project_name}-api-gw"
  protocol_type = "HTTP"
  description   = "API Gateway for RAG Query Lambda Function"

  cors_configuration {
    allow_origins = ["https://d2h33zz3k8plgu.cloudfront.net"]
    allow_methods = ["*"]
    allow_headers = ["*"]
    max_age       = 300
  }
}

resource "aws_apigatewayv2_integration" "rag_api_integration" {
  api_id             = aws_apigatewayv2_api.rag_api_gateway.id
  integration_type   = "AWS_PROXY"
  # ❗️FIX 1: Removed 'integration_method = "POST"'
  integration_uri    = aws_lambda_function.api_query_service.invoke_arn
  # ❗️FIX 2: Changed payload version to 1.0 to match your Python code
  payload_format_version = "1.0"
}

# ❗️FIX 3: Deleted the old 'ANY' route and created three specific routes
# All routes point to the same integration
resource "aws_apigatewayv2_route" "rag_api_route_query" {
  api_id    = aws_apigatewayv2_api.rag_api_gateway.id
  route_key = "POST /query"
  target    = "integrations/${aws_apigatewayv2_integration.rag_api_integration.id}"
}

resource "aws_apigatewayv2_route" "rag_api_route_list_files" {
  api_id    = aws_apigatewayv2_api.rag_api_gateway.id
  route_key = "GET /list-files"
  target    = "integrations/${aws_apigatewayv2_integration.rag_api_integration.id}"
}

resource "aws_apigatewayv2_route" "rag_api_catchall" {
  api_id    = aws_apigatewayv2_api.rag_api_gateway.id
  route_key = "ANY /{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.rag_api_integration.id}"
}

resource "aws_apigatewayv2_route" "rag_api_route_get_upload_url" {
  api_id    = aws_apigatewayv2_api.rag_api_gateway.id
  route_key = "GET /get-upload-url"
  target    = "integrations/${aws_apigatewayv2_integration.rag_api_integration.id}"
}

resource "aws_apigatewayv2_deployment" "rag_api_deployment" {
  api_id = aws_apigatewayv2_api.rag_api_gateway.id
  
  # ❗️FIX 4: 'depends_on' must now include all new routes
  depends_on = [
    aws_apigatewayv2_route.rag_api_route_query,
    aws_apigatewayv2_route.rag_api_route_list_files,
    aws_apigatewayv2_route.rag_api_route_get_upload_url,
  ]
}

resource "aws_cloudwatch_log_group" "api_access_logs" {
  name              = "/aws/apigateway/${aws_apigatewayv2_api.rag_api_gateway.id}/${var.environment}"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-api-access-logs"
  }
}

resource "aws_apigatewayv2_stage" "rag_api_stage" {
  api_id      = aws_apigatewayv2_api.rag_api_gateway.id
  name        = var.environment
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_access_logs.arn
    format = jsonencode({
      requestId             = "$context.requestId"
      requestTime           = "$context.requestTime"
      httpMethod            = "$context.httpMethod"
      path                  = "$context.routeKey" # This will now show the specific route
      status                = "$context.status"
      integrationLatency    = "$context.integrationLatency"
      integrationStatus     = "$context.integrationStatus"
      integrationErrorMessage = "$context.integrationErrorMessage"
    })
  }

  default_route_settings {
    throttling_burst_limit = 500
    throttling_rate_limit  = 500
  }

  depends_on = [
    aws_apigatewayv2_deployment.rag_api_deployment, # Stage depends on deployment
    aws_api_gateway_account.apigw_account_settings,
  ]
}

resource "aws_lambda_permission" "apigw_lambda_permission" {
  statement_id  = "AllowAPIGatewayInvokeLambda"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api_query_service.function_name
  principal     = "apigateway.amazonaws.com"

  # Updated source_arn to be more robust for all routes
  source_arn = "${aws_apigatewayv2_api.rag_api_gateway.execution_arn}/*/*/*"
}