# Production Environment Configuration - MAXIMUM SECURITY

# Basic Configuration
project_name = "pdfquery"
environment  = "production"
aws_region   = "us-east-1"
aws_profile  = "default"

# Security Configuration - MAXIMUM SECURITY ENABLED
enable_lambda_vpc          = true   # Lambda in private subnets with NAT Gateway
enable_mfa_enforcement     = true   # Require MFA for all users
enable_guardduty           = true   # Threat detection
enable_config              = true   # Compliance AWSCONFIG monitoring
log_retention_days         = 7     # CloudWatch log retention
enable_s3_replication      = false  # Cross-region backup
backup_region              = "us-east-1"

# WAF Configuration - Israel Only
enable_waf_geo_blocking    = true
allowed_countries          = ["IL"]

# Lambda Configuration
ingestion_version = 20
api_version       = 1
layer_version     = 1

# Docker Image Tags
ingestion_image_tag = "latest"
api_image_tag       = "latest"
agent_image_tag     = "latest"

# Admin User Configuration (optional)
admin_email    = ""  # Set to create admin user: "admin@company.com"
admin_password = ""  # Min 12 chars with complexity

# Alert Configuration (optional)
alert_email = "alon.salasi@leidos.com"  # Set to receive security alerts: "security@company.com"

# SES Configuration
ses_sender_email = ""  # Verified sender email for agent to send emails: "noreply@company.com"


