# Cognito User Pool for Authentication
resource "aws_cognito_user_pool" "agent_users" {
  name = "${var.project_name}-user-pool"

  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = true
  }

  mfa_configuration = "OPTIONAL"

  software_token_mfa_configuration {
    enabled = true
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  user_pool_add_ons {
    advanced_security_mode = "ENFORCED"
  }

  auto_verified_attributes = ["email"]
  
  email_configuration {
    email_sending_account = "COGNITO_DEFAULT"
  }
  
  username_configuration {
    case_sensitive = false
  }

  device_configuration {
    challenge_required_on_new_device      = true
    device_only_remembered_on_user_prompt = true
  }

  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
    mutable             = false
  }

  schema {
    name                = "phone_number"
    attribute_data_type = "String"
    required            = false
    mutable             = true
  }

  tags = {
    Name = "${var.project_name}-user-pool"
  }

  lifecycle {
    ignore_changes = [schema]
  }
}

resource "aws_cognito_user_pool_client" "agent_client" {
  name         = "${var.project_name}-client"
  user_pool_id = aws_cognito_user_pool.agent_users.id

  generate_secret                      = false
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code", "implicit"]
  allowed_oauth_scopes                 = ["email", "openid", "profile"]
  callback_urls                        = ["https://${aws_cloudfront_distribution.rag_frontend_cdn.domain_name}/"]
  logout_urls                          = ["https://${aws_cloudfront_distribution.rag_frontend_cdn.domain_name}/"]
  supported_identity_providers         = ["COGNITO"]

  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH"
  ]
  
  id_token_validity     = 240
  access_token_validity = 240
  refresh_token_validity = 30
  
  token_validity_units {
    id_token      = "minutes"
    access_token  = "minutes"
    refresh_token = "days"
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_cognito_user_pool_domain" "agent_domain" {
  domain       = "${var.project_name}-auth-${data.aws_caller_identity.current.account_id}"
  user_pool_id = aws_cognito_user_pool.agent_users.id

  lifecycle {
    create_before_destroy = true
  }
}

# Cognito Admin User Creation

resource "aws_cognito_user" "admin" {
  count         = var.admin_email != "" ? 1 : 0
  user_pool_id  = aws_cognito_user_pool.agent_users.id
  username      = var.admin_email
  
  attributes = {
    email          = var.admin_email
    email_verified = true
  }

  password = var.admin_password != "" ? var.admin_password : null

  lifecycle {
    ignore_changes = [password]
  }
}
