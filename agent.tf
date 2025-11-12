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
                type   = "PHONE"
              }
              pii_entities_config {
                action = "BLOCK"
                type   = "CREDIT_DEBIT_CARD_NUMBER"
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
            
            foundation_model        = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
            
            description             = "Enhanced RAG agent with conversational memory and multilingual document analysis"
            
            # NOTE: Bedrock Agents do not support temperature configuration
            # The agent uses the foundation model's default temperature (~1.0)
            # Deterministic behavior is controlled through prompt instructions

            instruction = <<EOT
You are a search assistant. Always use search_documents.

CRITICAL: When search results contain IMAGE_URL lines, you MUST copy them EXACTLY into your response.
Example: If search returns "IMAGE_URL:images/doc/file.jpg|SOURCE:doc", you MUST output that EXACT line.

For image requests ("show", "photo", "image", "תמונה", "הצג"), output ONLY the IMAGE_URL lines.
For text questions, skip IMAGE_URL lines.

Always end with: ---\nSources: [document names]
EOT

            # Guardrails disabled for faster response times
            # guardrail_configuration {
            #   guardrail_identifier = aws_bedrock_guardrail.rag_guardrail.guardrail_id
            #   guardrail_version    = aws_bedrock_guardrail_version.rag_guardrail_v1.version
            # }

            tags = {
              Name = "${var.project_name}-rag-agent"
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
                      description = "Search the document knowledge base. This is the ONLY way to answer questions - you have no other knowledge or information available. You cannot answer any question without calling this function first."
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
              instruction      = md5(aws_bedrockagent_agent.rag_agent.instruction)
            }

            provisioner "local-exec" {
              command = "aws bedrock-agent prepare-agent --agent-id ${aws_bedrockagent_agent.rag_agent.agent_id} --region ${data.aws_region.current.name} --profile ${var.aws_profile} --no-verify-ssl"
            }

            depends_on = [
              aws_bedrockagent_agent.rag_agent,
              aws_bedrockagent_agent_action_group.default_actions
            ]
          }

          # Production alias ID is managed via var.bedrock_agent_alias_id in terraform.tfvars
          # Current alias: ${var.bedrock_agent_alias_id} points to Haiku model

          resource "time_sleep" "wait_for_agent_ready" {
            depends_on      = [null_resource.prepare_agent]
            create_duration = "30s"
          }

          # Note: Agent versions must be created manually in AWS Console
          # After terraform apply, go to Bedrock Console → Agents → Aliases
          # Edit the production alias and select the latest DRAFT to create a new version

