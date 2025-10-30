# Automated Frontend Deployment

resource "aws_s3_object" "frontend" {
  bucket       = aws_s3_bucket.frontend.id
  key          = "index.html"
  source       = "${path.module}/index.html"
  content_type = "text/html"
  etag         = filemd5("${path.module}/index.html")

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
      try {
        if (!(Test-Path '${path.module}/index.html')) {
          Write-Error "Source file not found: ${path.module}/index.html"
          exit 1
        }
        $tempFile = New-TemporaryFile
        $content = Get-Content -Path '${path.module}/index.html' -Raw -ErrorAction Stop
        $content = $content -replace 'USER_POOL_ID_PLACEHOLDER', '${aws_cognito_user_pool.agent_users.id}'
        $content = $content -replace 'CLIENT_ID_PLACEHOLDER', '${aws_cognito_user_pool_client.agent_client.id}'
        $content = $content -replace 'COGNITO_DOMAIN_PLACEHOLDER', '${aws_cognito_user_pool_domain.agent_domain.domain}'
        $content = $content -replace 'API_GATEWAY_URL_PLACEHOLDER', '${aws_apigatewayv2_stage.rag_api_stage.invoke_url}'
        $content | Out-File -FilePath $tempFile -Encoding UTF8 -ErrorAction Stop
        aws s3 cp $tempFile s3://${aws_s3_bucket.frontend.id}/index.html --content-type text/html --profile ${var.aws_profile}
        Remove-Item $tempFile
        if ($LASTEXITCODE -ne 0) {
          Write-Error "S3 upload failed with exit code $LASTEXITCODE"
          exit $LASTEXITCODE
        }
      } catch {
        Write-Error "Frontend deployment failed: $_"
        exit 1
      }
    EOT

    on_failure = fail
  }

  depends_on = [
    aws_cognito_user_pool.agent_users,
    aws_cognito_user_pool_client.agent_client,
    aws_apigatewayv2_stage.rag_api_stage
  ]
}
