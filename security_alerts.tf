# =========================================================
# Security Alerts - Standard Implementation
# Cost: ~$7/month for comprehensive security monitoring
# =========================================================

# =========================================================
# EventBridge Rules for Instant Security Alerts (FREE)
# =========================================================

# 1. Cognito User Creation Alert
resource "aws_cloudwatch_event_rule" "cognito_user_created" {
  name        = "${var.project_name}-cognito-user-created"
  description = "Alert when new Cognito user is created"

  event_pattern = jsonencode({
    source      = ["aws.cognito-idp"]
    detail-type = ["AWS API Call via CloudTrail"]
    detail = {
      eventName = ["AdminCreateUser", "SignUp"]
    }
  })
}

resource "aws_cloudwatch_event_target" "cognito_user_created_to_sns" {
  rule      = aws_cloudwatch_event_rule.cognito_user_created.name
  target_id = "SendToSNS"
  arn       = aws_sns_topic.security_alerts.arn

  input_transformer {
    input_paths = {
      user   = "$.detail.requestParameters.username"
      time   = "$.time"
      source = "$.detail.sourceIPAddress"
    }
    input_template = "\"🚨 SECURITY ALERT: New User Created\\n\\nUser: <user>\\nTime: <time>\\nSource IP: <source>\\n\\nAction: Verify this user creation was authorized.\""
  }
}

# 2. Password Change Alert
resource "aws_cloudwatch_event_rule" "password_changed" {
  name        = "${var.project_name}-password-changed"
  description = "Alert when user password is changed"

  event_pattern = jsonencode({
    source      = ["aws.cognito-idp"]
    detail-type = ["AWS API Call via CloudTrail"]
    detail = {
      eventName = ["ChangePassword", "AdminSetUserPassword", "ForgotPassword"]
    }
  })
}

resource "aws_cloudwatch_event_target" "password_changed_to_sns" {
  rule      = aws_cloudwatch_event_rule.password_changed.name
  target_id = "SendToSNS"
  arn       = aws_sns_topic.security_alerts.arn

  input_transformer {
    input_paths = {
      event  = "$.detail.eventName"
      user   = "$.detail.requestParameters.username"
      time   = "$.time"
      source = "$.detail.sourceIPAddress"
    }
    input_template = "\"🔐 SECURITY ALERT: Password Changed\\n\\nEvent: <event>\\nUser: <user>\\nTime: <time>\\nSource IP: <source>\\n\\nAction: Verify this password change was authorized.\""
  }
}

# 3. IAM Policy Changes Alert
resource "aws_cloudwatch_event_rule" "iam_policy_changed" {
  name        = "${var.project_name}-iam-policy-changed"
  description = "Alert when IAM policies are modified"

  event_pattern = jsonencode({
    source      = ["aws.iam"]
    detail-type = ["AWS API Call via CloudTrail"]
    detail = {
      eventName = [
        "PutRolePolicy",
        "DeleteRolePolicy",
        "AttachRolePolicy",
        "DetachRolePolicy",
        "PutUserPolicy",
        "DeleteUserPolicy"
      ]
    }
  })
}

resource "aws_cloudwatch_event_target" "iam_policy_changed_to_sns" {
  rule      = aws_cloudwatch_event_rule.iam_policy_changed.name
  target_id = "SendToSNS"
  arn       = aws_sns_topic.security_alerts.arn

  input_transformer {
    input_paths = {
      event    = "$.detail.eventName"
      role     = "$.detail.requestParameters.roleName"
      user     = "$.detail.userIdentity.principalId"
      time     = "$.time"
      source   = "$.detail.sourceIPAddress"
    }
    input_template = "\"⚠️ CRITICAL ALERT: IAM Policy Modified\\n\\nEvent: <event>\\nRole/User: <role>\\nModified By: <user>\\nTime: <time>\\nSource IP: <source>\\n\\nAction: Investigate immediately - potential privilege escalation.\""
  }
}

# 4. S3 Bucket Policy Changes Alert
resource "aws_cloudwatch_event_rule" "s3_policy_changed" {
  name        = "${var.project_name}-s3-policy-changed"
  description = "Alert when S3 bucket policies are modified"

  event_pattern = jsonencode({
    source      = ["aws.s3"]
    detail-type = ["AWS API Call via CloudTrail"]
    detail = {
      eventName = [
        "PutBucketPolicy",
        "DeleteBucketPolicy",
        "PutBucketAcl",
        "PutBucketPublicAccessBlock"
      ]
    }
  })
}

resource "aws_cloudwatch_event_target" "s3_policy_changed_to_sns" {
  rule      = aws_cloudwatch_event_rule.s3_policy_changed.name
  target_id = "SendToSNS"
  arn       = aws_sns_topic.security_alerts.arn

  input_transformer {
    input_paths = {
      event  = "$.detail.eventName"
      bucket = "$.detail.requestParameters.bucketName"
      user   = "$.detail.userIdentity.principalId"
      time   = "$.time"
      source = "$.detail.sourceIPAddress"
    }
    input_template = "\"⚠️ CRITICAL ALERT: S3 Bucket Policy Modified\\n\\nEvent: <event>\\nBucket: <bucket>\\nModified By: <user>\\nTime: <time>\\nSource IP: <source>\\n\\nAction: Verify bucket is not publicly accessible.\""
  }
}

# 5. Security Group Changes Alert
resource "aws_cloudwatch_event_rule" "security_group_changed" {
  name        = "${var.project_name}-security-group-changed"
  description = "Alert when security groups are modified"

  event_pattern = jsonencode({
    source      = ["aws.ec2"]
    detail-type = ["AWS API Call via CloudTrail"]
    detail = {
      eventName = [
        "AuthorizeSecurityGroupIngress",
        "AuthorizeSecurityGroupEgress",
        "RevokeSecurityGroupIngress",
        "RevokeSecurityGroupEgress",
        "CreateSecurityGroup",
        "DeleteSecurityGroup"
      ]
    }
  })
}

resource "aws_cloudwatch_event_target" "security_group_changed_to_sns" {
  rule      = aws_cloudwatch_event_rule.security_group_changed.name
  target_id = "SendToSNS"
  arn       = aws_sns_topic.security_alerts.arn

  input_transformer {
    input_paths = {
      event  = "$.detail.eventName"
      sg     = "$.detail.requestParameters.groupId"
      user   = "$.detail.userIdentity.principalId"
      time   = "$.time"
      source = "$.detail.sourceIPAddress"
    }
    input_template = "\"⚠️ SECURITY ALERT: Security Group Modified\\n\\nEvent: <event>\\nSecurity Group: <sg>\\nModified By: <user>\\nTime: <time>\\nSource IP: <source>\\n\\nAction: Verify no unauthorized ports are open.\""
  }
}

# 6. GuardDuty Findings Alert (HIGH/CRITICAL only)
resource "aws_cloudwatch_event_rule" "guardduty_findings" {
  name        = "${var.project_name}-guardduty-findings"
  description = "Alert on HIGH and CRITICAL GuardDuty findings"

  event_pattern = jsonencode({
    source      = ["aws.guardduty"]
    detail-type = ["GuardDuty Finding"]
    detail = {
      severity = [7, 7.0, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 8, 8.0, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9]
    }
  })
}

resource "aws_cloudwatch_event_target" "guardduty_findings_to_sns" {
  rule      = aws_cloudwatch_event_rule.guardduty_findings.name
  target_id = "SendToSNS"
  arn       = aws_sns_topic.security_alerts.arn

  input_transformer {
    input_paths = {
      finding    = "$.detail.type"
      severity   = "$.detail.severity"
      resource   = "$.detail.resource.resourceType"
      time       = "$.time"
      account    = "$.detail.accountId"
      region     = "$.detail.region"
    }
    input_template = "\"🚨 CRITICAL ALERT: GuardDuty Threat Detected\\n\\nFinding: <finding>\\nSeverity: <severity>\\nResource: <resource>\\nAccount: <account>\\nRegion: <region>\\nTime: <time>\\n\\nAction: Investigate immediately in GuardDuty console.\""
  }
}

# =========================================================
# CloudWatch Metric Filters for Log-Based Alerts
# =========================================================

# 7. Failed Login Attempts Filter
resource "aws_cloudwatch_log_metric_filter" "failed_logins" {
  name           = "${var.project_name}-failed-logins"
  log_group_name = aws_cloudwatch_log_group.lambda_agent_logs.name
  pattern        = "[time, request_id, level=ERROR*, msg=\"*authentication*failed*\" || msg=\"*login*failed*\" || msg=\"*invalid*credentials*\"]"

  metric_transformation {
    name      = "FailedLoginAttempts"
    namespace = "${var.project_name}/Security"
    value     = "1"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_metric_alarm" "failed_login_spike" {
  alarm_name          = "${var.project_name}-failed-login-spike"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "FailedLoginAttempts"
  namespace           = "${var.project_name}/Security"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  alarm_description   = "Multiple failed login attempts detected - possible brute force attack"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.security_alerts.arn]
}

# 8. Mass File Download Filter
resource "aws_cloudwatch_log_metric_filter" "mass_downloads" {
  name           = "${var.project_name}-mass-downloads"
  log_group_name = aws_cloudwatch_log_group.lambda_agent_logs.name
  pattern        = "[time, request_id, level, msg=\"*view-file*\" || msg=\"*download*\" || msg=\"*get-image*\"]"

  metric_transformation {
    name      = "FileDownloads"
    namespace = "${var.project_name}/Security"
    value     = "1"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_metric_alarm" "mass_download_alert" {
  alarm_name          = "${var.project_name}-mass-download-alert"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "FileDownloads"
  namespace           = "${var.project_name}/Security"
  period              = 300
  statistic           = "Sum"
  threshold           = 10
  alarm_description   = "Mass file download detected - possible data exfiltration"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.security_alerts.arn]
}

# 9. Bulk File Deletion Filter
resource "aws_cloudwatch_log_metric_filter" "bulk_deletions" {
  name           = "${var.project_name}-bulk-deletions"
  log_group_name = aws_cloudwatch_log_group.lambda_agent_logs.name
  pattern        = "[time, request_id, level, msg=\"*delete-file*\" || msg=\"*file*deleted*\"]"

  metric_transformation {
    name      = "FileDeletions"
    namespace = "${var.project_name}/Security"
    value     = "1"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_metric_alarm" "bulk_deletion_alert" {
  alarm_name          = "${var.project_name}-bulk-deletion-alert"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "FileDeletions"
  namespace           = "${var.project_name}/Security"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  alarm_description   = "Bulk file deletion detected - possible ransomware or sabotage"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.security_alerts.arn]
}

# 10. Large Query Volume Filter
resource "aws_cloudwatch_log_metric_filter" "query_volume" {
  name           = "${var.project_name}-query-volume"
  log_group_name = aws_cloudwatch_log_group.lambda_agent_logs.name
  pattern        = "[time, request_id, level, msg=\"*agent-query*\" || msg=\"*Processing query*\"]"

  metric_transformation {
    name      = "QueryVolume"
    namespace = "${var.project_name}/Security"
    value     = "1"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_metric_alarm" "query_volume_alert" {
  alarm_name          = "${var.project_name}-query-volume-alert"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "QueryVolume"
  namespace           = "${var.project_name}/Security"
  period              = 300
  statistic           = "Sum"
  threshold           = 20
  alarm_description   = "Unusually high query volume - possible automated scraping"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.security_alerts.arn]
}

# =========================================================
# CloudWatch Anomaly Detection (8 Metrics)
# Cost: $2.40/month
# =========================================================

# 1. API Gateway Request Count Anomaly
resource "aws_cloudwatch_metric_alarm" "api_requests_anomaly" {
  alarm_name          = "${var.project_name}-api-requests-anomaly"
  comparison_operator = "LessThanLowerOrGreaterThanUpperThreshold"
  evaluation_periods  = 2
  threshold_metric_id = "e1"
  alarm_description   = "Unusual API request pattern detected"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.security_alerts.arn]

  metric_query {
    id          = "e1"
    expression  = "ANOMALY_DETECTION_BAND(m1)"
    label       = "API Requests (Expected)"
    return_data = "true"
  }

  metric_query {
    id          = "m1"
    return_data = "true"
    metric {
      metric_name = "Count"
      namespace   = "AWS/ApiGateway"
      period      = 300
      stat        = "Sum"
      dimensions = {
        ApiId = aws_apigatewayv2_api.rag_api_gateway.id
      }
    }
  }
}

# 2. Lambda Invocation Anomaly
resource "aws_cloudwatch_metric_alarm" "lambda_invocations_anomaly" {
  alarm_name          = "${var.project_name}-lambda-invocations-anomaly"
  comparison_operator = "LessThanLowerOrGreaterThanUpperThreshold"
  evaluation_periods  = 2
  threshold_metric_id = "e1"
  alarm_description   = "Unusual Lambda invocation pattern detected"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.security_alerts.arn]

  metric_query {
    id          = "e1"
    expression  = "ANOMALY_DETECTION_BAND(m1)"
    label       = "Lambda Invocations (Expected)"
    return_data = "true"
  }

  metric_query {
    id          = "m1"
    return_data = "true"
    metric {
      metric_name = "Invocations"
      namespace   = "AWS/Lambda"
      period      = 300
      stat        = "Sum"
      dimensions = {
        FunctionName = aws_lambda_function.agent_executor.function_name
      }
    }
  }
}

# 3. Lambda Duration Anomaly
resource "aws_cloudwatch_metric_alarm" "lambda_duration_anomaly" {
  alarm_name          = "${var.project_name}-lambda-duration-anomaly"
  comparison_operator = "LessThanLowerOrGreaterThanUpperThreshold"
  evaluation_periods  = 2
  threshold_metric_id = "e1"
  alarm_description   = "Unusual Lambda execution time - possible performance issue"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.security_alerts.arn]

  metric_query {
    id          = "e1"
    expression  = "ANOMALY_DETECTION_BAND(m1)"
    label       = "Lambda Duration (Expected)"
    return_data = "true"
  }

  metric_query {
    id          = "m1"
    return_data = "true"
    metric {
      metric_name = "Duration"
      namespace   = "AWS/Lambda"
      period      = 300
      stat        = "Average"
      dimensions = {
        FunctionName = aws_lambda_function.agent_executor.function_name
      }
    }
  }
}

# 4. API Gateway Latency Anomaly
resource "aws_cloudwatch_metric_alarm" "api_latency_anomaly" {
  alarm_name          = "${var.project_name}-api-latency-anomaly"
  comparison_operator = "LessThanLowerOrGreaterThanUpperThreshold"
  evaluation_periods  = 2
  threshold_metric_id = "e1"
  alarm_description   = "Unusual API latency detected"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.security_alerts.arn]

  metric_query {
    id          = "e1"
    expression  = "ANOMALY_DETECTION_BAND(m1)"
    label       = "API Latency (Expected)"
    return_data = "true"
  }

  metric_query {
    id          = "m1"
    return_data = "true"
    metric {
      metric_name = "IntegrationLatency"
      namespace   = "AWS/ApiGateway"
      period      = 300
      stat        = "Average"
      dimensions = {
        ApiId = aws_apigatewayv2_api.rag_api_gateway.id
      }
    }
  }
}

# 5. S3 GET Requests Anomaly
resource "aws_cloudwatch_metric_alarm" "s3_get_anomaly" {
  alarm_name          = "${var.project_name}-s3-get-anomaly"
  comparison_operator = "LessThanLowerOrGreaterThanUpperThreshold"
  evaluation_periods  = 2
  threshold_metric_id = "e1"
  alarm_description   = "Unusual S3 GET request pattern - possible data exfiltration"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.security_alerts.arn]

  metric_query {
    id          = "e1"
    expression  = "ANOMALY_DETECTION_BAND(m1)"
    label       = "S3 GET Requests (Expected)"
    return_data = "true"
  }

  metric_query {
    id          = "m1"
    return_data = "true"
    metric {
      metric_name = "GetRequests"
      namespace   = "AWS/S3"
      period      = 300
      stat        = "Sum"
      dimensions = {
        BucketName = aws_s3_bucket.rag_documents.bucket
      }
    }
  }
}

# 6. S3 PUT Requests Anomaly
resource "aws_cloudwatch_metric_alarm" "s3_put_anomaly" {
  alarm_name          = "${var.project_name}-s3-put-anomaly"
  comparison_operator = "LessThanLowerOrGreaterThanUpperThreshold"
  evaluation_periods  = 2
  threshold_metric_id = "e1"
  alarm_description   = "Unusual S3 PUT request pattern - possible bulk upload"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.security_alerts.arn]

  metric_query {
    id          = "e1"
    expression  = "ANOMALY_DETECTION_BAND(m1)"
    label       = "S3 PUT Requests (Expected)"
    return_data = "true"
  }

  metric_query {
    id          = "m1"
    return_data = "true"
    metric {
      metric_name = "PutRequests"
      namespace   = "AWS/S3"
      period      = 300
      stat        = "Sum"
      dimensions = {
        BucketName = aws_s3_bucket.rag_documents.bucket
      }
    }
  }
}

# 7. Lambda Error Rate Anomaly
resource "aws_cloudwatch_metric_alarm" "lambda_errors_anomaly" {
  alarm_name          = "${var.project_name}-lambda-errors-anomaly"
  comparison_operator = "LessThanLowerOrGreaterThanUpperThreshold"
  evaluation_periods  = 2
  threshold_metric_id = "e1"
  alarm_description   = "Unusual Lambda error pattern detected"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.security_alerts.arn]

  metric_query {
    id          = "e1"
    expression  = "ANOMALY_DETECTION_BAND(m1)"
    label       = "Lambda Errors (Expected)"
    return_data = "true"
  }

  metric_query {
    id          = "m1"
    return_data = "true"
    metric {
      metric_name = "Errors"
      namespace   = "AWS/Lambda"
      period      = 300
      stat        = "Sum"
      dimensions = {
        FunctionName = aws_lambda_function.agent_executor.function_name
      }
    }
  }
}

# 8. API Gateway 4xx Error Anomaly
resource "aws_cloudwatch_metric_alarm" "api_4xx_anomaly" {
  alarm_name          = "${var.project_name}-api-4xx-anomaly"
  comparison_operator = "LessThanLowerOrGreaterThanUpperThreshold"
  evaluation_periods  = 2
  threshold_metric_id = "e1"
  alarm_description   = "Unusual 4xx error pattern - possible API abuse or scanning"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.security_alerts.arn]

  metric_query {
    id          = "e1"
    expression  = "ANOMALY_DETECTION_BAND(m1)"
    label       = "API 4xx Errors (Expected)"
    return_data = "true"
  }

  metric_query {
    id          = "m1"
    return_data = "true"
    metric {
      metric_name = "4XXError"
      namespace   = "AWS/ApiGateway"
      period      = 300
      stat        = "Sum"
      dimensions = {
        ApiId = aws_apigatewayv2_api.rag_api_gateway.id
      }
    }
  }
}

# =========================================================
# SNS Topic Permissions for EventBridge
# =========================================================

resource "aws_sns_topic_policy" "security_alerts_eventbridge" {
  arn = aws_sns_topic.security_alerts.arn

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid = "AllowEventBridgePublish"
        Effect = "Allow"
        Principal = {
          Service = "events.amazonaws.com"
        }
        Action   = "SNS:Publish"
        Resource = aws_sns_topic.security_alerts.arn
      },
      {
        Sid = "AllowCloudWatchPublish"
        Effect = "Allow"
        Principal = {
          Service = "cloudwatch.amazonaws.com"
        }
        Action   = "SNS:Publish"
        Resource = aws_sns_topic.security_alerts.arn
      }
    ]
  })
}
