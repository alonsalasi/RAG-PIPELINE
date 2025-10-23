resource "aws_apigatewayv2_api" "rag_api_gateway" {
  name          = "${var.project_name}-api-gw"
  protocol_type = "HTTP"
  description   = "API Gateway for RAG Query Lambda Function"

  # Core CORS settings (HTTP API handles OPTIONS implicitly with these headers)
  cors_configuration {
    allow_origins = ["*"] 
    allow_methods = ["POST", "GET", "OPTIONS", "PUT"] 
    allow_headers = ["content-type"]
    max_age       = 300
  }
}

# --- 1. Integration for POST/GET/OPTIONS (Lambda Proxy) ---
resource "aws_apigatewayv2_integration" "rag_api_integration" {
  api_id             = aws_apigatewayv2_api.rag_api_gateway.id
  integration_type   = "AWS_PROXY"
  integration_method = "POST"
  integration_uri    = aws_lambda_function.api_query_service.invoke_arn
  payload_format_version = "2.0" 
}

# --- 2. Route for Core API Calls (Handles all methods including implicit OPTIONS) ---
resource "aws_apigatewayv2_route" "rag_api_route" {
  api_id    = aws_apigatewayv2_api.rag_api_gateway.id
  # The "ANY" method ensures all HTTP methods (POST, GET, OPTIONS, PUT) 
  # are routed. HTTP API's built-in CORS handles the OPTIONS response.
  route_key = "ANY /{proxy+}" 
  target    = "integrations/${aws_apigatewayv2_integration.rag_api_integration.id}"
}

resource "aws_apigatewayv2_deployment" "rag_api_deployment" {
  api_id      = aws_apigatewayv2_api.rag_api_gateway.id
  # Dependency on the single, catch-all route
  depends_on  = [aws_apigatewayv2_route.rag_api_route]
}

# --- CloudWatch Log Group for API Access Logs ---
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
  
  # Enable Access Logging on the Stage
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_access_logs.arn
    format = jsonencode({
      requestId               = "$context.requestId"
      requestTime             = "$context.requestTime"
      httpMethod              = "$context.httpMethod"
      path                    = "$context.routeKey"
      status                  = "$context.status"
      integrationLatency      = "$context.integrationLatency"
      integrationStatus       = "$context.integrationStatus"
      integrationErrorMessage = "$context.integrationErrorMessage"
    })
  }

  depends_on = [
    aws_apigatewayv2_route.rag_api_route,
    aws_api_gateway_account.apigw_account_settings, 
  ]
}

resource "aws_lambda_permission" "apigw_lambda_permission" {
  statement_id  = "AllowAPIGatewayInvokeLambda"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api_query_service.function_name
  principal     = "apigateway.amazonaws.com"

  source_arn = "${aws_apigatewayv2_api.rag_api_gateway.execution_arn}/*/*"
}