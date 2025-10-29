# Cognito User Pool for Authentication
resource "aws_cognito_user_pool" "agent_users" {
  name = "${var.project_name}-user-pool"

  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = true
  }

  mfa_configuration = var.enable_mfa_enforcement ? "ON" : "OPTIONAL"

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

  tags = {
    Name = "${var.project_name}-user-pool"
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
}

resource "aws_cognito_user_pool_domain" "agent_domain" {
  domain       = "${var.project_name}-auth-${data.aws_caller_identity.current.account_id}"
  user_pool_id = aws_cognito_user_pool.agent_users.id
}
