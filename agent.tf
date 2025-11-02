# agent.tf

# =========================================================
# Bedrock Guardrails for Secure Agent
# =========================================================
resource "aws_bedrock_guardrail" "rag_guardrail" {
  name                      = "${var.project_name}-guardrail"
  description               = "Security guardrails for RAG agent"
  blocked_input_messaging   = "I cannot process this request due to content policy."
  blocked_outputs_messaging = "I cannot provide this response due to content policy."

  content_policy_config {
    filters_config {
      input_strength  = "MEDIUM"
      output_strength = "MEDIUM"
      type            = "HATE"
    }
    filters_config {
      input_strength  = "MEDIUM"
      output_strength = "MEDIUM"
      type            = "SEXUAL"
    }
  }

  sensitive_information_policy_config {
    pii_entities_config {
      action = "BLOCK"
      type   = "EMAIL"
    }
    pii_entities_config {
      action = "BLOCK"
      type   = "PHONE"
    }
    pii_entities_config {
      action = "BLOCK"
      type   = "CREDIT_DEBIT_CARD_NUMBER"
    }
    pii_entities_config {
      action = "BLOCK"
      type   = "US_SOCIAL_SECURITY_NUMBER"
    }
  }

  tags = {
    Name = "${var.project_name}-guardrail"
  }
}

resource "aws_bedrock_guardrail_version" "rag_guardrail_v1" {
  guardrail_arn = aws_bedrock_guardrail.rag_guardrail.guardrail_arn
  description   = "Version 1"
}

# =========================================================
# Bedrock Agent Definition with Guardrails
# =========================================================
resource "aws_bedrockagent_agent" "rag_agent" {
  agent_name              = "${var.project_name}-rag-agent"
  agent_resource_role_arn = aws_iam_role.bedrock_agent_role.arn
  
  foundation_model        = "us.anthropic.claude-3-5-sonnet-20241022-v2:0"
  
  description             = "Enhanced RAG agent with conversational memory and multilingual document analysis"

  instruction = <<EOF
You are a car catalog assistant. For EVERY user query:
1. ALWAYS call search_documents function with the user's query
2. If the result contains lines starting with 'IMAGE_URL:', return ONLY those lines
3. Otherwise, provide a helpful answer based on the search results

IMPORTANT: You MUST call search_documents for every query. Never say you cannot find images without calling search_documents first.
EOF

  guardrail_configuration {
    guardrail_identifier = aws_bedrock_guardrail.rag_guardrail.guardrail_id
    guardrail_version    = aws_bedrock_guardrail_version.rag_guardrail_v1.version
  }

  tags = {
    Name = "${var.project_name}-rag-agent"
  }

  lifecycle {
    ignore_changes = [guardrail_configuration]
  }
}

# =========================================================
# Bedrock Agent Action Group
# =========================================================
resource "aws_bedrockagent_agent_action_group" "default_actions" {
  agent_id          = aws_bedrockagent_agent.rag_agent.agent_id
  agent_version     = "DRAFT" # Action groups are always attached to the DRAFT version
  action_group_name = "LambdaTools"

  api_schema {
    payload = jsonencode({
      openapi = "3.0.0"
      info = {
        title   = "Document Search and Email API"
        version = "1.0.0"
      }
      paths = {
        "/search" = {
          post = {
            description = "Search and analyze documents in the knowledge base"
            operationId = "search_documents"
            requestBody = {
              required = true
              content = {
                "application/json" = {
                  schema = {
                    type = "object"
                    properties = {
                      query = {
                        type        = "string"
                        description = "The search query or question about the documents"
                      }
                    }
                    required = ["query"]
                  }
                }
              }
            }
            responses = {
              "200" = {
                description = "Successful response"
                content = {
                  "application/json" = {
                    schema = {
                      type = "object"
                      properties = {
                        result = {
                          type = "string"
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
        "/send-email" = {
          post = {
            description = "Send an email to a specified recipient"
            operationId = "send_email"
            requestBody = {
              required = true
              content = {
                "application/json" = {
                  schema = {
                    type = "object"
                    properties = {
                      to_email = {
                        type        = "string"
                        description = "Recipient email address"
                      }
                      subject = {
                        type        = "string"
                        description = "Email subject line"
                      }
                      body = {
                        type        = "string"
                        description = "Email body content"
                      }
                    }
                    required = ["to_email", "subject", "body"]
                  }
                }
              }
            }
            responses = {
              "200" = {
                description = "Email sent successfully"
                content = {
                  "application/json" = {
                    schema = {
                      type = "object"
                      properties = {
                        result = {
                          type = "string"
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    })
  }

  action_group_executor {
    lambda = aws_lambda_function.agent_executor.arn
  }

  depends_on = [
    aws_lambda_function.agent_executor,
    aws_bedrockagent_agent.rag_agent
  ]
}

# =========================================================
# Prepare the Agent (CRITICAL STEP)
# =========================================================
resource "null_resource" "prepare_agent" {
  triggers = {
    agent_id         = aws_bedrockagent_agent.rag_agent.agent_id
    foundation_model = aws_bedrockagent_agent.rag_agent.foundation_model
    instruction      = aws_bedrockagent_agent.rag_agent.instruction
  }

  provisioner "local-exec" {
    command = "aws bedrock-agent prepare-agent --agent-id ${aws_bedrockagent_agent.rag_agent.agent_id} --region ${data.aws_region.current.name} --profile ${var.aws_profile}"
  }

  depends_on = [
    aws_bedrockagent_agent.rag_agent,
    aws_bedrockagent_agent_action_group.default_actions
  ]
}

# Import existing production alias: terraform import aws_bedrockagent_agent_alias.production 19RBXR8RAY,8YWB06TOFD
resource "aws_bedrockagent_agent_alias" "production" {
  agent_id         = aws_bedrockagent_agent.rag_agent.agent_id
  agent_alias_name = "production"
  description      = "Production alias for RAG agent"
  
  routing_configuration {
    agent_version = "41"
  }

  depends_on = [null_resource.prepare_agent]
}

resource "time_sleep" "wait_for_agent_ready" {
  depends_on      = [null_resource.prepare_agent]
  create_duration = "60s"
}

# Production alias is created by null_resource.update_production_alias