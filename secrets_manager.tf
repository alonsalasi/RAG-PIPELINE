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

resource "aws_secretsmanager_secret" "google_vision_key" {
  name                    = "${var.project_name}-google-vision-key"
  description             = "Google Vision API key for handwriting recognition"
  kms_key_id              = aws_kms_key.agent_encryption.arn
  recovery_window_in_days = 7

  tags = {
    Name = "${var.project_name}-google-vision-key"
  }
}

resource "aws_secretsmanager_secret_version" "google_vision_key" {
  secret_id = aws_secretsmanager_secret.google_vision_key.id
  secret_string = jsonencode({
    api_key = var.google_vision_api_key != "" ? var.google_vision_api_key : "NOT_CONFIGURED"
  })
}
