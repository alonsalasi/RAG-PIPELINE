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
      type            = "VIOLENCE"
    }
    filters_config {
      input_strength  = "MEDIUM"
      output_strength = "MEDIUM"
      type            = "SEXUAL"
    }
    filters_config {
      input_strength  = "MEDIUM"
      output_strength = "MEDIUM"
      type            = "INSULTS"
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
  
  foundation_model        = "amazon.nova-pro-v1:0"
  
  description             = "Enhanced RAG agent with conversational memory and multilingual document analysis"

  instruction = "You are an expert data analyst that extracts and reasons over information from documents provided via RAG. Your goal is to give the most complete, accurate, and evidence-based answer possible using the retrieved documents. Follow these rules strictly: 1. Always synthesize information — if the answer is implied or can be inferred logically from the data, include it clearly. 2. Never respond with 'I cannot find an answer' unless the concept is entirely missing. Instead, give your best reasoned inference based on related info. 3. Include exact quotes or data from the PDF when relevant (e.g., engine specs, configurations, tables, or key phrases). 4. If multiple possible answers exist, list them all and clarify context (e.g., different trims or regions). 5. FOR IMAGE REQUESTS: If user asks to show/see/display/view images or pictures, return ONLY the IMAGE_URL lines from search results. NO text before or after. NO descriptions. NO explanations. Just copy the IMAGE_URL lines exactly. 6. Your output should be concise but information-rich, and structured whenever possible (e.g., bullet points or JSON-like blocks). 7. When unsure, reason based on evidence in the documents and state the degree of certainty if relevant. Act as a domain expert and research analyst — accurate, confident, and precise."

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

resource "null_resource" "update_production_alias" {
  triggers = {
    instruction = aws_bedrockagent_agent.rag_agent.instruction
  }

  provisioner "local-exec" {
    interpreter = ["powershell", "-Command"]
    command = "$alias = aws bedrock-agent list-agent-aliases --agent-id ${aws_bedrockagent_agent.rag_agent.agent_id} --profile ${var.aws_profile} | ConvertFrom-Json; $prodAlias = $alias.agentAliasSummaries | Where-Object {$_.agentAliasName -eq 'production'}; if ($prodAlias) { aws bedrock-agent delete-agent-alias --agent-id ${aws_bedrockagent_agent.rag_agent.agent_id} --agent-alias-id $prodAlias.agentAliasId --profile ${var.aws_profile}; Start-Sleep 10 }; aws bedrock-agent create-agent-alias --agent-id ${aws_bedrockagent_agent.rag_agent.agent_id} --agent-alias-name production --description 'Production alias for RAG agent' --profile ${var.aws_profile}"
  }

  depends_on = [null_resource.prepare_agent]
}

resource "time_sleep" "wait_for_agent_ready" {
  depends_on      = [null_resource.prepare_agent]
  create_duration = "60s"
}

# Production alias is created by null_resource.update_production_alias