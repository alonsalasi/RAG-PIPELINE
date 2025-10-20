resource "aws_secretsmanager_secret" "rds_master_credentials" {
  name        = "${var.project_name}-rds-master-credentials"
  description = "RDS PostgreSQL master username and password"
}

resource "aws_secretsmanager_secret_version" "rds_master_credentials_version" {
  secret_id = aws_secretsmanager_secret.rds_master_credentials.id

  secret_string = jsonencode({
    username = var.rds_username,
    password = var.rds_password
  })
}

data "aws_secretsmanager_secret_version" "rds_password_value" {
  secret_id = aws_secretsmanager_secret.rds_master_credentials.id
}
