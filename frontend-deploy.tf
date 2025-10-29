# Automated Frontend Deployment

resource "aws_s3_object" "frontend" {
  bucket       = aws_s3_bucket.rag_frontend.id
  key          = "index.html"
  source       = "${path.module}/index-auth.html"
  content_type = "text/html"
  etag         = filemd5("${path.module}/index-auth.html")

  lifecycle {
    ignore_changes = [source]
  }
}

resource "null_resource" "update_frontend_config" {
  triggers = {
    cognito_pool_id   = aws_cognito_user_pool.agent_users.id
    cognito_client_id = aws_cognito_user_pool_client.agent_client.id
    api_url           = aws_apigatewayv2_stage.rag_api_stage.invoke_url
  }

  provisioner "local-exec" {
    interpreter = ["powershell", "-Command"]
    command     = <<-EOT
      $content = Get-Content -Path '${path.module}/index-auth.html' -Raw
      $content = $content -replace 'USER_POOL_ID_PLACEHOLDER', '${aws_cognito_user_pool.agent_users.id}'
      $content = $content -replace 'CLIENT_ID_PLACEHOLDER', '${aws_cognito_user_pool_client.agent_client.id}'
      $content = $content -replace 'COGNITO_DOMAIN_PLACEHOLDER', '${aws_cognito_user_pool_domain.agent_domain.domain}'
      $content = $content -replace 'API_GATEWAY_URL_PLACEHOLDER', '${aws_apigatewayv2_stage.rag_api_stage.invoke_url}'
      $content | Out-File -FilePath '${path.module}/index.html' -Encoding UTF8
      aws s3 cp '${path.module}/index.html' s3://${aws_s3_bucket.rag_frontend.id}/index.html --content-type text/html
    EOT
  }

  depends_on = [
    aws_cognito_user_pool.agent_users,
    aws_cognito_user_pool_client.agent_client,
    aws_apigatewayv2_stage.rag_api_stage
  ]
}
