# Security and Authentication Outputs
output "cognito_user_pool_id" {
  value       = aws_cognito_user_pool.agent_users.id
  description = "Cognito User Pool ID for authentication"
}

output "cognito_client_id" {
  value       = aws_cognito_user_pool_client.agent_client.id
  description = "Cognito Client ID for frontend"
}

output "cognito_domain" {
  value       = "https://${aws_cognito_user_pool_domain.agent_domain.domain}.auth.${data.aws_region.current.name}.amazoncognito.com"
  description = "Cognito hosted UI domain"
}

output "cloudfront_url" {
  value       = "https://${aws_cloudfront_distribution.rag_frontend_cdn.domain_name}"
  description = "CloudFront URL for accessing the application"
}

output "api_gateway_url" {
  value       = aws_apigatewayv2_stage.rag_api_stage.invoke_url
  description = "API Gateway URL (requires authentication)"
}
