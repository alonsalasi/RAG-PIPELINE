# Default Account Configuration

# Basic Configuration
project_name = "pdfquery"
environment  = "production"
aws_region   = "us-west-2"
aws_profile  = "default"

# Security Configuration
enable_lambda_vpc          = false
enable_mfa_enforcement     = true
enable_guardduty           = true
enable_config              = true
log_retention_days         = 90
enable_s3_replication      = false
backup_region              = "us-east-1"

# WAF Configuration
enable_waf_geo_blocking    = false
allowed_countries          = []

# Lambda Configuration
ingestion_version = 20
api_version       = 1
layer_version     = 1

# Docker Image Tags
ingestion_image_tag = "latest"
api_image_tag       = "latest"
agent_image_tag     = "latest"

# Admin User Configuration
admin_email    = ""
admin_password = ""

# Alert Configuration
alert_email = ""

# SES Configuration
ses_sender_email = ""
