# RAG Document Analysis System - Production Deployment

## Quick Start (Fully Automated)

### 1. Configure Variables

Edit `terraform.tfvars`:

```hcl
# Basic Configuration
project_name = "pdfquery"
environment  = "production"
aws_region   = "us-west-2"

# Admin User (will be created automatically)
admin_email    = "admin@yourcompany.com"
admin_password = "YourSecurePass123!@#"

# Security Alerts
alert_email = "security@yourcompany.com"

# Security Configuration
enable_lambda_vpc      = true
enable_mfa_enforcement = true
log_retention_days     = 90
```

### 2. Deploy Everything

```bash
terraform init
terraform plan
terraform apply
```

That's it! Terraform will automatically:
- ✅ Create all AWS infrastructure (VPC, Lambda, API Gateway, Cognito, etc.)
- ✅ Build and push Docker images to ECR
- ✅ Create admin user in Cognito
- ✅ Deploy frontend with correct configuration
- ✅ Set up CloudWatch alarms with email alerts
- ✅ Configure all security controls

### 3. Access Your Application

```bash
# Get the CloudFront URL
terraform output cloudfront_url
```

Open the URL in your browser and login with your admin credentials.

---

## What Gets Deployed

### Infrastructure (80+ resources)
- **VPC**: Private/public subnets, NAT Gateway, VPC endpoints
- **Lambda**: Ingestion worker + Agent executor (in private subnets)
- **API Gateway**: JWT-protected REST API
- **Cognito**: User pool with MFA support
- **S3**: Document storage + backup bucket (encrypted)
- **CloudFront**: CDN for frontend
- **KMS**: Encryption keys with rotation
- **CloudTrail**: Audit logging
- **GuardDuty**: Threat detection
- **AWS Config**: Compliance monitoring
- **WAF**: Rate limiting + SQL injection protection
- **CloudWatch**: Logs + alarms + metrics
- **SNS**: Security alert notifications
- **Secrets Manager**: Bedrock configuration

### Security Features
- 🔒 All data encrypted at rest (KMS)
- 🔒 All data encrypted in transit (TLS 1.2+)
- 🔒 Lambda in private subnets with NAT Gateway
- 🔒 MFA enforcement on Cognito
- 🔒 JWT authentication on all API routes
- 🔒 WAF protection (500 req/IP/5min)
- 🔒 GuardDuty threat detection
- 🔒 CloudTrail audit logging
- 🔒 90-day log retention
- 🔒 Automated security alarms

### Cost
- **With VPC (Maximum Security)**: ~$113-131/month
- **Without VPC (Standard Security)**: ~$22-32/month

---

## Configuration Options

### Minimal Configuration (Testing)
```hcl
enable_lambda_vpc      = false
enable_mfa_enforcement = false
log_retention_days     = 30
admin_email            = ""  # Create user manually
alert_email            = ""  # No alerts
```
**Cost**: ~$16-24/month

### Standard Production
```hcl
enable_lambda_vpc      = false
enable_mfa_enforcement = true
log_retention_days     = 90
admin_email            = "admin@company.com"
alert_email            = "security@company.com"
```
**Cost**: ~$22-32/month

### Maximum Security (Current Default)
```hcl
enable_lambda_vpc      = true
enable_mfa_enforcement = true
log_retention_days     = 90
api_allowed_ip_ranges  = ["YOUR_COMPANY_IPS"]
admin_email            = "admin@company.com"
alert_email            = "security@company.com"
```
**Cost**: ~$113-131/month

---

## Outputs

After deployment, get important values:

```bash
terraform output cloudfront_url          # Frontend URL
terraform output api_gateway_url         # API endpoint
terraform output cognito_user_pool_id    # User pool ID
terraform output cognito_client_id       # Client ID
```

---

## Post-Deployment

### Confirm Email Subscription
Check your email (`alert_email`) and confirm the SNS subscription to receive security alerts.

### Login to Application
1. Open CloudFront URL
2. Login with admin credentials
3. Upload documents and start querying

### Monitor Security
- CloudWatch alarms will email you on issues
- Review GuardDuty findings in AWS Console
- Check CloudTrail logs for audit trail

---

## Updating

### Update Infrastructure
```bash
terraform plan
terraform apply
```

### Update Lambda Code
```bash
# Increment version in terraform.tfvars
ingestion_version = 21

# Apply changes
terraform apply
```

### Update Frontend
```bash
# Edit index-auth.html
# Apply changes
terraform apply
```

---

## Rollback

```bash
terraform destroy
```

---

## Documentation

- **SECURITY-CHECKLIST.md** - Complete security verification
- **README-SECURITY.md** - Security architecture overview
- **scripts/validate-security.ps1** - Automated security checks

---

## Support

- AWS Support: https://console.aws.amazon.com/support/
- Terraform Issues: https://github.com/hashicorp/terraform/issues

---

**Version**: 1.0  
**Last Updated**: 2024-01-15
