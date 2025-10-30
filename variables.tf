variable "aws_region" {
  description = "The AWS region to deploy the infrastructure"
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "AWS CLI profile to use"
  type        = string
  default     = "leidos"
}

variable "region" {
  description = "AWS region for resource ARNs"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "A unique prefix for all resources"
  type        = string
  default     = "rag-ecs-project"
}

variable "environment" {
  description = "Project Enviroment"
  type        = string
  default     = "default"
}

variable "api_version" {
  description = "Lambda_API_Version"
  type = number
  default = 1
}

variable "ingestion_image_tag" {
  description = "Docker image tag for ingestion Lambda (e.g., 'latest')."
  type        = string
  default     = "latest"
}

variable "api_image_tag" {
  description = "Docker image tag for api Lambda (e.g., 'latest')."
  type        = string
  default     = "latest"
}

variable "ingestion_version" {
  description = "Lambda_Ingestion_Version"
  type = number
  default = 20
}

variable "layer_version" {
  description = "Lambda_Layer_Version"
  type = number
  default = 1
}

variable "agent_image_tag" {
  description = "Docker image tag for Agent Lambda"
  type        = string
  default     = "latest"
}

# Security Configuration (Maximum Security Defaults)
variable "enable_lambda_vpc" {
  description = "Enable VPC for Lambda functions (adds ~$85/month for NAT Gateway)"
  type        = bool
  default     = true
}

variable "enable_guardduty" {
  description = "Enable AWS GuardDuty threat detection"
  type        = bool
  default     = true
}

variable "enable_config" {
  description = "Enable AWS Config for compliance monitoring"
  type        = bool
  default     = true
}

variable "enable_waf_geo_blocking" {
  description = "Enable WAF geographic blocking"
  type        = bool
  default     = true
}

variable "allowed_countries" {
  description = "List of allowed country codes for WAF geo-blocking"
  type        = list(string)
  default     = ["IL"]
}

variable "enable_mfa_enforcement" {
  description = "Enforce MFA for all Cognito users"
  type        = bool
  default     = true
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 90
}

variable "enable_s3_replication" {
  description = "Enable S3 cross-region replication"
  type        = bool
  default     = false
}

variable "backup_region" {
  description = "AWS region for backup replication"
  type        = string
  default     = "us-east-1"
}

variable "alert_email" {
  description = "Email address for security alerts"
  type        = string
  default     = ""
}

variable "ses_sender_email" {
  description = "Verified sender email address for SES"
  type        = string
  default     = ""
}

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