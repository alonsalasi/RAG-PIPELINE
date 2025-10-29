# AWS SES for Email Sending

resource "aws_ses_email_identity" "sender" {
  count = var.ses_sender_email != "" ? 1 : 0
  email = var.ses_sender_email
}

resource "aws_ses_configuration_set" "agent_emails" {
  name = "${var.project_name}-agent-emails"
}

resource "aws_ses_event_destination" "cloudwatch" {
  name                   = "cloudwatch-destination"
  configuration_set_name = aws_ses_configuration_set.agent_emails.name
  enabled                = true
  matching_types         = ["send", "reject", "bounce", "complaint", "delivery"]

  cloudwatch_destination {
    default_value  = "default"
    dimension_name = "ses:configuration-set"
    value_source   = "messageTag"
  }
}
