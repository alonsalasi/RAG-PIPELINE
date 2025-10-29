# Enterprise Security Checklist for Production Deployment

## ✅ Implemented Security Controls

### 1. **Encryption at Rest**
- ✅ KMS encryption for all S3 buckets (rag_documents, audit_logs, config_logs, backup)
- ✅ KMS encryption for Lambda environment variables
- ✅ KMS encryption for SQS queues (ingestion queue, DLQ)
- ✅ KMS encryption for CloudWatch Logs
- ✅ KMS key rotation enabled (automatic annual rotation)
- ✅ Secrets Manager with KMS encryption for sensitive configs

### 2. **Encryption in Transit**
- ✅ HTTPS/TLS enforced on API Gateway
- ✅ VPC endpoints use AWS PrivateLink (encrypted)
- ✅ CloudFront with TLS 1.2+ minimum

### 3. **Identity & Access Management**
- ✅ Cognito User Pool with JWT authentication
- ✅ Strong password policy (12+ chars, complexity requirements)
- ✅ MFA support (configurable enforcement via `enable_mfa_enforcement`)
- ✅ Advanced security mode enabled (adaptive authentication, compromised credentials detection)
- ✅ Device tracking enabled
- ✅ IAM roles with least-privilege policies
- ✅ No hardcoded credentials (using Secrets Manager)

### 4. **Network Security**
- ✅ VPC with public/private subnets
- ✅ Security groups with minimal egress (HTTPS only)
- ✅ NAT Gateway for private subnet internet access (optional via `enable_lambda_vpc`)
- ✅ VPC endpoints for AWS services (Bedrock, S3, SQS, SNS, KMS, Secrets Manager, CloudWatch)
- ✅ Lambda in private subnets (optional, configurable)
- ✅ No public ingress to Lambda functions

### 5. **Web Application Firewall (WAF)**
- ✅ Rate limiting (500 requests/IP/5min)
- ✅ AWS Managed Rules: Common Rule Set
- ✅ AWS Managed Rules: Known Bad Inputs
- ✅ AWS Managed Rules: SQL Injection protection
- ✅ Geographic blocking (optional via `enable_waf_geo_blocking`)
- ✅ IP allowlisting (optional via `api_allowed_ip_ranges`)

### 6. **Logging & Monitoring**
- ✅ CloudTrail enabled (all Lambda invocations, S3 object access)
- ✅ CloudWatch Logs with 90-day retention
- ✅ API Gateway access logs
- ✅ S3 access logging
- ✅ X-Ray tracing enabled on Lambda functions
- ✅ CloudWatch alarms for errors, 4xx responses, WAF blocks

### 7. **Threat Detection & Compliance**
- ✅ AWS GuardDuty enabled (S3 protection, malware scanning)
- ✅ AWS Config enabled (compliance monitoring)
- ✅ Bedrock Guardrails (content filtering, PII blocking)

### 8. **Data Protection**
- ✅ S3 versioning enabled
- ✅ S3 lifecycle policies (archive to Glacier, delete old versions)
- ✅ S3 public access blocked on all buckets
- ✅ S3 backup bucket with replication (optional via `enable_s3_replication`)
- ✅ Dead Letter Queue for failed Lambda invocations

### 9. **API Security**
- ✅ JWT authorization on all API routes
- ✅ CORS restricted to CloudFront domain only
- ✅ API Gateway throttling (500 req/sec burst, 500 req/sec steady)

### 10. **Resource Tagging**
- ✅ Consistent tagging strategy (Name, Environment, CostCenter, Compliance)

---

## 🔧 Configuration for Production

### Required Actions Before Deployment:

1. **Set Security Variables** in `terraform.tfvars`:
```hcl
# Enable VPC for Lambda (adds ~$100/month for NAT Gateway)
enable_lambda_vpc = true  # Recommended for production

# Enable MFA enforcement
enable_mfa_enforcement = true  # Highly recommended

# Set log retention
log_retention_days = 90  # Or 365 for compliance

# Enable S3 replication for disaster recovery
enable_s3_replication = true
backup_region = "us-east-1"

# Optional: IP Allowlisting (restrict API to company IPs)
api_allowed_ip_ranges = ["203.0.113.0/24", "198.51.100.0/24"]

# Optional: Geographic blocking (allow only specific countries)
enable_waf_geo_blocking = true
allowed_countries = ["US", "IL"]
```

2. **Create Initial Cognito User**:
```bash
aws cognito-idp admin-create-user \
  --user-pool-id <POOL_ID> \
  --username admin@company.com \
  --user-attributes Name=email,Value=admin@company.com \
  --temporary-password "TempPass123!" \
  --message-action SUPPRESS
```

3. **Enable MFA for Admin User**:
```bash
aws cognito-idp admin-set-user-mfa-preference \
  --user-pool-id <POOL_ID> \
  --username admin@company.com \
  --software-token-mfa-settings Enabled=true,PreferredMfa=true
```

4. **Review IAM Policies**:
- Ensure least-privilege access
- Remove wildcard `Resource = "*"` where possible
- Scope KMS/Secrets Manager to specific ARNs

5. **Set Up CloudWatch Alarms SNS Topic**:
```bash
aws sns create-topic --name pdfquery-security-alerts
aws sns subscribe --topic-arn <TOPIC_ARN> --protocol email --notification-endpoint security@company.com
```

6. **Enable GuardDuty Notifications**:
- Configure EventBridge rule to send GuardDuty findings to SNS/Slack

7. **Configure AWS Config Rules**:
- Add compliance rules for your organization's requirements
- Example: encrypted-volumes, s3-bucket-public-read-prohibited

---

## 💰 Cost Breakdown (Monthly Estimates)

### Base Security (Always On):
- KMS: ~$1/key/month + $0.03/10k requests = **~$3/month**
- CloudTrail: ~$2/month (first trail free, data events charged)
- CloudWatch Logs (90-day retention): ~$5-10/month
- WAF: $5/month + $1/million requests = **~$6-8/month**
- Cognito: Free tier (50k MAU), then $0.0055/MAU
- Secrets Manager: $0.40/secret/month = **~$0.40/month**
- **Total Base: ~$16-24/month**

### Optional Security (Configurable):
- **GuardDuty**: ~$4-6/month (S3 protection, malware scanning)
- **AWS Config**: ~$2/month (first 1000 rules free)
- **NAT Gateway** (if `enable_lambda_vpc = true`): **~$64/month** (2 AZs × $32)
- **VPC Endpoints** (if `enable_lambda_vpc = true`): **~$21/month** (7 endpoints × $0.01/hour)
- **S3 Replication** (if enabled): Variable based on data size
- **Total Optional: ~$91-99/month**

### **Total Security Cost:**
- **Without VPC**: ~$22-32/month
- **With VPC (Maximum Security)**: ~$113-131/month

---

## 🚨 Security Recommendations by Environment

### **Test/Dev Environment:**
```hcl
enable_lambda_vpc = false
enable_mfa_enforcement = false
enable_guardduty = true
enable_config = false
log_retention_days = 30
```
**Cost: ~$16-24/month**

### **Production Environment (Standard):**
```hcl
enable_lambda_vpc = false  # AWS services already secure via TLS+IAM
enable_mfa_enforcement = true
enable_guardduty = true
enable_config = true
log_retention_days = 90
api_allowed_ip_ranges = ["<YOUR_COMPANY_IPS>"]
```
**Cost: ~$22-32/month**

### **Production Environment (Maximum Security):**
```hcl
enable_lambda_vpc = true  # Private subnets + NAT Gateway
enable_mfa_enforcement = true
enable_guardduty = true
enable_config = true
enable_waf_geo_blocking = true
allowed_countries = ["US", "IL"]
log_retention_days = 365
enable_s3_replication = true
api_allowed_ip_ranges = ["<YOUR_COMPANY_IPS>"]
```
**Cost: ~$113-131/month**

---

## 🔍 Compliance Mappings

### SOC 2 Type II:
- ✅ Encryption at rest and in transit
- ✅ Access controls (Cognito + IAM)
- ✅ Audit logging (CloudTrail)
- ✅ Monitoring and alerting (CloudWatch)
- ✅ Change management (AWS Config)

### HIPAA:
- ✅ KMS encryption for PHI
- ✅ Access controls and MFA
- ✅ Audit trails (CloudTrail)
- ✅ Data backup and recovery
- ⚠️ **Additional Required**: BAA with AWS, encryption key management procedures

### GDPR:
- ✅ Data encryption
- ✅ Access controls
- ✅ Audit logging
- ✅ Data retention policies (S3 lifecycle)
- ⚠️ **Additional Required**: Data processing agreements, right to erasure implementation

### ISO 27001:
- ✅ Information security controls
- ✅ Access management
- ✅ Cryptographic controls
- ✅ Logging and monitoring
- ✅ Incident management (GuardDuty)

---

## 📋 Post-Deployment Security Validation

Run these checks after deployment:

```bash
# 1. Verify S3 buckets are not public
aws s3api get-bucket-acl --bucket <BUCKET_NAME>

# 2. Verify KMS encryption on S3
aws s3api get-bucket-encryption --bucket <BUCKET_NAME>

# 3. Verify CloudTrail is logging
aws cloudtrail get-trail-status --name pdfquery-agent-audit-trail

# 4. Verify GuardDuty is enabled
aws guardduty list-detectors

# 5. Verify WAF is attached to API Gateway
aws wafv2 list-web-acls --scope REGIONAL

# 6. Test API authentication (should fail without JWT)
curl -X POST https://<API_URL>/agent-query

# 7. Verify Lambda is in VPC (if enabled)
aws lambda get-function-configuration --function-name pdfquery-ingestion-worker

# 8. Check CloudWatch alarms
aws cloudwatch describe-alarms --alarm-names pdfquery-lambda-errors
```

---

## 🛡️ Security Best Practices

1. **Rotate Secrets Regularly**: Update Secrets Manager values every 90 days
2. **Review IAM Policies**: Quarterly audit of permissions
3. **Monitor GuardDuty Findings**: Set up automated alerts
4. **Patch Lambda Dependencies**: Rebuild Docker images monthly
5. **Review CloudTrail Logs**: Weekly security audits
6. **Test Disaster Recovery**: Quarterly backup restoration tests
7. **Update WAF Rules**: Review and adjust rate limits based on traffic
8. **Cognito User Audits**: Monthly review of active users
9. **Cost Optimization**: Review CloudWatch logs retention and VPC endpoint usage

---

## 📞 Security Incident Response

If a security incident is detected:

1. **Isolate**: Disable affected Lambda functions or API routes
2. **Investigate**: Review CloudTrail and GuardDuty findings
3. **Contain**: Update WAF rules to block malicious IPs
4. **Remediate**: Rotate compromised credentials in Secrets Manager
5. **Document**: Log incident details for compliance
6. **Notify**: Alert security team and stakeholders

---

**Last Updated**: 2024-01-15
**Security Review Required**: Quarterly
