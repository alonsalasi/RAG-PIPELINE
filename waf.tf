# WAF to protect API Gateway

resource "aws_wafv2_web_acl" "api_protection" {
  name  = "${var.project_name}-api-waf"
  scope = "REGIONAL"

  default_action {
    dynamic "allow" {
      for_each = var.enable_waf_geo_blocking ? [] : [1]
      content {}
    }
    dynamic "block" {
      for_each = var.enable_waf_geo_blocking ? [1] : []
      content {}
    }
  }

  # Geographic restriction (if enabled)
  dynamic "rule" {
    for_each = var.enable_waf_geo_blocking ? [1] : []
    content {
      name     = "AllowSpecificCountries"
      priority = 0

      action {
        allow {}
      }

      statement {
        geo_match_statement {
          country_codes = var.allowed_countries
        }
      }

      visibility_config {
        cloudwatch_metrics_enabled = true
        metric_name                = "AllowSpecificCountries"
        sampled_requests_enabled   = true
      }
    }
  }

  # Rate limiting
  rule {
    name     = "RateLimitRule"
    priority = 1

    action {
      block {
        custom_response {
          response_code = 429
        }
      }
    }

    statement {
      rate_based_statement {
        limit              = 500
        aggregate_key_type = "IP"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "RateLimitRule"
      sampled_requests_enabled   = true
    }
  }

  # AWS Managed Rules - Common Rule Set
  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 2

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "AWSManagedRulesCommonRuleSet"
      sampled_requests_enabled   = true
    }
  }

  # AWS Managed Rules - Known Bad Inputs
  rule {
    name     = "AWSManagedRulesKnownBadInputsRuleSet"
    priority = 3

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "AWSManagedRulesKnownBadInputsRuleSet"
      sampled_requests_enabled   = true
    }
  }

  # AWS Managed Rules - SQL Injection
  rule {
    name     = "AWSManagedRulesSQLiRuleSet"
    priority = 4

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesSQLiRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "AWSManagedRulesSQLiRuleSet"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.project_name}-api-waf"
    sampled_requests_enabled   = true
  }

  tags = {
    Name = "${var.project_name}-api-waf"
  }
}

resource "aws_wafv2_web_acl_association" "api_waf_association" {
  resource_arn = aws_apigatewayv2_stage.rag_api_stage.arn
  web_acl_arn  = aws_wafv2_web_acl.api_protection.arn
}
