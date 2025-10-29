# Cognito Admin User Creation

variable "admin_email" {
  description = "Admin user email address"
  type        = string
  default     = ""
}

variable "admin_password" {
  description = "Admin user password (min 12 chars)"
  type        = string
  sensitive   = true
  default     = ""
}

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
