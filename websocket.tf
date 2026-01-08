# WebSocket API Gateway
resource "aws_apigatewayv2_api" "websocket" {
  name                       = "pdfquery-websocket-${var.environment}"
  protocol_type              = "WEBSOCKET"
  route_selection_expression = "$request.body.action"
  
  tags = {
    Name        = "pdfquery-websocket-${var.environment}"
    Environment = var.environment
  }
}

# REQUEST Authorizer for WebSocket (uses existing agent_executor Lambda)
resource "aws_apigatewayv2_authorizer" "websocket_cognito" {
  api_id           = aws_apigatewayv2_api.websocket.id
  authorizer_type  = "REQUEST"
  authorizer_uri   = aws_lambda_function.agent_executor.invoke_arn
  identity_sources = ["route.request.querystring.token"]
  name             = "cognito-authorizer"
}

# Lambda Permission for WebSocket Authorizer
resource "aws_lambda_permission" "websocket_authorizer" {
  statement_id  = "AllowAPIGatewayInvokeAuthorizer"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.agent_executor.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.websocket.execution_arn}/authorizers/${aws_apigatewayv2_authorizer.websocket_cognito.id}"
}

# WebSocket Stage
resource "aws_apigatewayv2_stage" "websocket" {
  api_id      = aws_apigatewayv2_api.websocket.id
  name        = var.environment
  auto_deploy = true
  
  default_route_settings {
    throttling_burst_limit = 500
    throttling_rate_limit  = 100
  }
}

# WebSocket Routes - all point to existing agent_executor Lambda
resource "aws_apigatewayv2_route" "connect" {
  api_id             = aws_apigatewayv2_api.websocket.id
  route_key          = "$connect"
  target             = "integrations/${aws_apigatewayv2_integration.websocket.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = aws_apigatewayv2_authorizer.websocket_cognito.id
}

resource "aws_apigatewayv2_route" "disconnect" {
  api_id    = aws_apigatewayv2_api.websocket.id
  route_key = "$disconnect"
  target    = "integrations/${aws_apigatewayv2_integration.websocket.id}"
}

resource "aws_apigatewayv2_route" "query" {
  api_id    = aws_apigatewayv2_api.websocket.id
  route_key = "query"
  target    = "integrations/${aws_apigatewayv2_integration.websocket.id}"
}

# Single integration to existing agent_executor Lambda
resource "aws_apigatewayv2_integration" "websocket" {
  api_id           = aws_apigatewayv2_api.websocket.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.agent_executor.invoke_arn
}

# Lambda Permission for WebSocket API Gateway
resource "aws_lambda_permission" "websocket" {
  statement_id  = "AllowExecutionFromWebSocketAPI"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.agent_executor.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.websocket.execution_arn}/*/*"
}

# Update agent_executor IAM role to allow WebSocket management
resource "aws_iam_role_policy" "agent_executor_websocket" {
  name = "pdfquery-agent-executor-websocket-${var.environment}"
  role = aws_iam_role.lambda_agent_role.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "execute-api:ManageConnections"
        ]
        Resource = "${aws_apigatewayv2_api.websocket.execution_arn}/*/*"
      }
    ]
  })
}

# Output WebSocket URL
output "websocket_url" {
  value       = "${aws_apigatewayv2_api.websocket.api_endpoint}/${aws_apigatewayv2_stage.websocket.name}"
  description = "WebSocket API URL"
}
