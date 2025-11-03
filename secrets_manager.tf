# =========================================================
# Secrets Manager for Sensitive Configuration
# =========================================================
resource "aws_secretsmanager_secret" "bedrock_config" {
  name                    = "${var.project_name}-bedrock-config"
  description             = "Bedrock Agent configuration"
  kms_key_id              = aws_kms_key.agent_encryption.arn
  recovery_window_in_days = 7

  tags = {
    Name = "${var.project_name}-bedrock-config"
  }
}

resource "aws_secretsmanager_secret_version" "bedrock_config" {
  secret_id = aws_secretsmanager_secret.bedrock_config.id
  secret_string = jsonencode({
    agent_id    = aws_bedrockagent_agent.rag_agent.agent_id
    agent_alias = "production"
    model_id    = "amazon.titan-embed-text-v1"
  })
}

resource "aws_secretsmanager_secret" "abbyy_cloud_key" {
  name                    = "${var.project_name}-abbyy-cloud-key"
  description             = "ABBYY Cloud OCR API credentials for handwriting recognition"
  kms_key_id              = aws_kms_key.agent_encryption.arn
  recovery_window_in_days = 7

  tags = {
    Name = "${var.project_name}-abbyy-cloud-key"
  }
}

resource "aws_secretsmanager_secret_version" "abbyy_cloud_key" {
  secret_id = aws_secretsmanager_secret.abbyy_cloud_key.id
  secret_string = jsonencode({
    application_id = var.abbyy_application_id != "" ? var.abbyy_application_id : "NOT_CONFIGURED"
    password       = var.abbyy_password != "" ? var.abbyy_password : "NOT_CONFIGURED"
  })
}
