resource "aws_apigatewayv2_api" "rag_api_gateway" {
  name          = "${var.project_name}-api-gw"
  protocol_type = "HTTP"
  description   = "API Gateway for RAG Query Lambda Function"

  cors_configuration {
    allow_origins = ["https://${aws_cloudfront_distribution.rag_frontend_cdn.domain_name}"]
    allow_methods = ["GET", "POST", "DELETE", "OPTIONS"]
    allow_headers = ["Content-Type", "Authorization", "X-Amz-Date", "X-Api-Key", "X-Amz-Security-Token"]
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
    issuer   = "https://cognito-idp.${data.aws_region.current.id}.amazonaws.com/${aws_cognito_user_pool.agent_users.id}"
  }
}

resource "aws_apigatewayv2_integration" "rag_api_integration" {
  api_id             = aws_apigatewayv2_api.rag_api_gateway.id
  integration_type   = "AWS_PROXY"
  integration_uri    = aws_lambda_function.agent_executor.invoke_arn
  payload_format_version = "1.0"
  timeout_milliseconds = 30000
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

resource "aws_apigatewayv2_route" "rag_api_route_upload" {
  api_id             = aws_apigatewayv2_api.rag_api_gateway.id
  route_key          = "POST /upload"
  target             = "integrations/${aws_apigatewayv2_integration.rag_api_integration.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito_authorizer.id
}

resource "aws_apigatewayv2_route" "rag_api_route_delete_file" {
  api_id             = aws_apigatewayv2_api.rag_api_gateway.id
  route_key          = "DELETE /delete-file"
  target             = "integrations/${aws_apigatewayv2_integration.rag_api_integration.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito_authorizer.id
}

resource "aws_apigatewayv2_route" "rag_api_route_cancel_upload" {
  api_id             = aws_apigatewayv2_api.rag_api_gateway.id
  route_key          = "DELETE /cancel-upload"
  target             = "integrations/${aws_apigatewayv2_integration.rag_api_integration.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito_authorizer.id
}

resource "aws_apigatewayv2_route" "rag_api_route_processing_status" {
  api_id             = aws_apigatewayv2_api.rag_api_gateway.id
  route_key          = "GET /processing-status"
  target             = "integrations/${aws_apigatewayv2_integration.rag_api_integration.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito_authorizer.id
}

resource "aws_apigatewayv2_route" "rag_api_route_agent_status" {
  api_id             = aws_apigatewayv2_api.rag_api_gateway.id
  route_key          = "GET /agent-status"
  target             = "integrations/${aws_apigatewayv2_integration.rag_api_integration.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito_authorizer.id
}

resource "aws_apigatewayv2_route" "rag_api_route_view_file" {
  api_id             = aws_apigatewayv2_api.rag_api_gateway.id
  route_key          = "GET /view-file"
  target             = "integrations/${aws_apigatewayv2_integration.rag_api_integration.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito_authorizer.id
}

resource "aws_apigatewayv2_route" "rag_api_route_autofill_extract" {
  api_id             = aws_apigatewayv2_api.rag_api_gateway.id
  route_key          = "POST /autofill/extract-source"
  target             = "integrations/${aws_apigatewayv2_integration.rag_api_integration.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito_authorizer.id
}

resource "aws_apigatewayv2_route" "rag_api_route_autofill_match" {
  api_id             = aws_apigatewayv2_api.rag_api_gateway.id
  route_key          = "POST /autofill/match-fields"
  target             = "integrations/${aws_apigatewayv2_integration.rag_api_integration.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito_authorizer.id
}

resource "aws_apigatewayv2_route" "rag_api_route_autofill_fill" {
  api_id             = aws_apigatewayv2_api.rag_api_gateway.id
  route_key          = "POST /autofill/fill-document"
  target             = "integrations/${aws_apigatewayv2_integration.rag_api_integration.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito_authorizer.id
}

resource "aws_apigatewayv2_route" "rag_api_route_save_chat" {
  api_id             = aws_apigatewayv2_api.rag_api_gateway.id
  route_key          = "POST /save-chat"
  target             = "integrations/${aws_apigatewayv2_integration.rag_api_integration.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito_authorizer.id
}

resource "aws_apigatewayv2_route" "rag_api_route_list_chats" {
  api_id             = aws_apigatewayv2_api.rag_api_gateway.id
  route_key          = "GET /list-chats"
  target             = "integrations/${aws_apigatewayv2_integration.rag_api_integration.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito_authorizer.id
}

resource "aws_apigatewayv2_route" "rag_api_route_get_chat" {
  api_id             = aws_apigatewayv2_api.rag_api_gateway.id
  route_key          = "GET /get-chat"
  target             = "integrations/${aws_apigatewayv2_integration.rag_api_integration.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito_authorizer.id
}

resource "aws_apigatewayv2_route" "rag_api_route_delete_chat" {
  api_id             = aws_apigatewayv2_api.rag_api_gateway.id
  route_key          = "DELETE /delete-chat"
  target             = "integrations/${aws_apigatewayv2_integration.rag_api_integration.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito_authorizer.id
}

resource "aws_apigatewayv2_deployment" "rag_api_deployment" {
  api_id = aws_apigatewayv2_api.rag_api_gateway.id
  
  triggers = {
    redeployment = sha1(join(",", [
      jsonencode(aws_apigatewayv2_route.rag_api_route_list_files),
      jsonencode(aws_apigatewayv2_route.rag_api_route_get_upload_url),
      jsonencode(aws_apigatewayv2_route.rag_api_route_agent_query),
      jsonencode(aws_apigatewayv2_route.rag_api_route_agent_analyze),
      jsonencode(aws_apigatewayv2_route.rag_api_route_get_image),
      jsonencode(aws_apigatewayv2_route.rag_api_route_upload),
      jsonencode(aws_apigatewayv2_route.rag_api_route_delete_file),
      jsonencode(aws_apigatewayv2_route.rag_api_route_cancel_upload),
      jsonencode(aws_apigatewayv2_route.rag_api_route_processing_status),
      jsonencode(aws_apigatewayv2_route.rag_api_route_agent_status),
      jsonencode(aws_apigatewayv2_route.rag_api_route_view_file),
      jsonencode(aws_apigatewayv2_route.rag_api_route_autofill_extract),
      jsonencode(aws_apigatewayv2_route.rag_api_route_autofill_match),
      jsonencode(aws_apigatewayv2_route.rag_api_route_autofill_fill),
      jsonencode(aws_apigatewayv2_route.rag_api_route_save_chat),
      jsonencode(aws_apigatewayv2_route.rag_api_route_list_chats),
      jsonencode(aws_apigatewayv2_route.rag_api_route_get_chat),
      jsonencode(aws_apigatewayv2_route.rag_api_route_delete_chat),
    ]))
  }
  
  depends_on = [
    aws_apigatewayv2_route.rag_api_route_list_files,
    aws_apigatewayv2_route.rag_api_route_get_upload_url,
    aws_apigatewayv2_route.rag_api_route_agent_query,
    aws_apigatewayv2_route.rag_api_route_agent_analyze,
    aws_apigatewayv2_route.rag_api_route_get_image,
    aws_apigatewayv2_route.rag_api_route_upload,
    aws_apigatewayv2_route.rag_api_route_delete_file,
    aws_apigatewayv2_route.rag_api_route_cancel_upload,
    aws_apigatewayv2_route.rag_api_route_processing_status,
    aws_apigatewayv2_route.rag_api_route_agent_status,
    aws_apigatewayv2_route.rag_api_route_view_file,
    aws_apigatewayv2_route.rag_api_route_autofill_extract,
    aws_apigatewayv2_route.rag_api_route_autofill_match,
    aws_apigatewayv2_route.rag_api_route_autofill_fill,
    aws_apigatewayv2_route.rag_api_route_save_chat,
    aws_apigatewayv2_route.rag_api_route_list_chats,
    aws_apigatewayv2_route.rag_api_route_get_chat,
    aws_apigatewayv2_route.rag_api_route_delete_chat,
    aws_apigatewayv2_integration.rag_api_integration
  ]
  
  lifecycle {
    create_before_destroy = true
  }
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
  api_id        = aws_apigatewayv2_api.rag_api_gateway.id
  name          = var.environment
  deployment_id = aws_apigatewayv2_deployment.rag_api_deployment.id
  auto_deploy   = false

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_access_logs.arn
    format = jsonencode({
      requestId             = "$context.requestId"
      requestTime           = "$context.requestTime"
      httpMethod            = "$context.httpMethod"
      path                  = "$context.routeKey"
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
    aws_apigatewayv2_deployment.rag_api_deployment,
    aws_api_gateway_account.apigw_account_settings,
    aws_cloudwatch_log_group.api_access_logs
  ]

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_lambda_permission" "apigw_lambda_permission" {
  statement_id  = "AllowAPIGatewayInvokeLambda"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.agent_executor.function_name
  principal     = "apigateway.amazonaws.com"

  source_arn = "${aws_apigatewayv2_api.rag_api_gateway.execution_arn}/*/*/*"
}