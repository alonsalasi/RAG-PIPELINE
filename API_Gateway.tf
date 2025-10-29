resource "aws_apigatewayv2_api" "rag_api_gateway" {
  name          = "${var.project_name}-api-gw"
  protocol_type = "HTTP"
  description   = "API Gateway for RAG Query Lambda Function"

  cors_configuration {
    allow_origins = ["https://${aws_cloudfront_distribution.rag_frontend_cdn.domain_name}"]
    allow_methods = ["*"]
    allow_headers = ["*"]
    max_age       = 300
  }
}

resource "aws_apigatewayv2_authorizer" "cognito_authorizer" {
  api_id           = aws_apigatewayv2_api.rag_api_gateway.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "cognito-authorizer"

  jwt_configuration {
    audience = [aws_cognito_user_pool_client.agent_client.id]
    issuer   = "https://cognito-idp.${data.aws_region.current.name}.amazonaws.com/${aws_cognito_user_pool.agent_users.id}"
  }
}

resource "aws_apigatewayv2_integration" "rag_api_integration" {
  api_id             = aws_apigatewayv2_api.rag_api_gateway.id
  integration_type   = "AWS_PROXY"
  integration_uri    = aws_lambda_function.agent_executor.invoke_arn
  payload_format_version = "1.0"
}

# ❗️FIX 3: Deleted the old 'ANY' route and created three specific routes
# All routes point to the same integration
# /query route removed - agent-only mode

resource "aws_apigatewayv2_route" "rag_api_route_list_files" {
  api_id             = aws_apigatewayv2_api.rag_api_gateway.id
  route_key          = "GET /list-files"
  target             = "integrations/${aws_apigatewayv2_integration.rag_api_integration.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito_authorizer.id
}

resource "aws_apigatewayv2_route" "rag_api_catchall" {
  api_id             = aws_apigatewayv2_api.rag_api_gateway.id
  route_key          = "ANY /{proxy+}"
  target             = "integrations/${aws_apigatewayv2_integration.rag_api_integration.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito_authorizer.id
}

resource "aws_apigatewayv2_route" "rag_api_route_get_upload_url" {
  api_id             = aws_apigatewayv2_api.rag_api_gateway.id
  route_key          = "GET /get-upload-url"
  target             = "integrations/${aws_apigatewayv2_integration.rag_api_integration.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito_authorizer.id
}

resource "aws_apigatewayv2_route" "rag_api_route_agent_query" {
  api_id             = aws_apigatewayv2_api.rag_api_gateway.id
  route_key          = "POST /agent-query"
  target             = "integrations/${aws_apigatewayv2_integration.rag_api_integration.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito_authorizer.id
}

resource "aws_apigatewayv2_route" "rag_api_route_agent_analyze" {
  api_id             = aws_apigatewayv2_api.rag_api_gateway.id
  route_key          = "POST /agent-analyze"
  target             = "integrations/${aws_apigatewayv2_integration.rag_api_integration.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito_authorizer.id
}

resource "aws_apigatewayv2_route" "rag_api_route_get_image" {
  api_id             = aws_apigatewayv2_api.rag_api_gateway.id
  route_key          = "GET /get-image"
  target             = "integrations/${aws_apigatewayv2_integration.rag_api_integration.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito_authorizer.id
}

resource "aws_apigatewayv2_deployment" "rag_api_deployment" {
  api_id = aws_apigatewayv2_api.rag_api_gateway.id
  
  # Updated dependencies for agent-only mode
  depends_on = [
    aws_apigatewayv2_route.rag_api_route_list_files,
    aws_apigatewayv2_route.rag_api_route_get_upload_url,
    aws_apigatewayv2_route.rag_api_route_agent_query,
    aws_apigatewayv2_route.rag_api_route_agent_analyze,
  ]
}

resource "aws_cloudwatch_log_group" "api_access_logs" {
  name              = "/aws/apigateway/${aws_apigatewayv2_api.rag_api_gateway.id}/${var.environment}"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.agent_encryption.arn

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
  function_name = aws_lambda_function.agent_executor.function_name
  principal     = "apigateway.amazonaws.com"

  source_arn = "${aws_apigatewayv2_api.rag_api_gateway.execution_arn}/*/*/*"
}