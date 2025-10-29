# KMS Key for encrypting all agent data
resource "aws_kms_key" "agent_encryption" {
  description             = "KMS key for encrypting agent data and transactions"
  deletion_window_in_days = 10
  enable_key_rotation     = true

  tags = {
    Name = "${var.project_name}-agent-encryption-key"
  }
}

resource "aws_kms_alias" "agent_encryption_alias" {
  name          = "alias/${var.project_name}-agent-key"
  target_key_id = aws_kms_key.agent_encryption.key_id
}
