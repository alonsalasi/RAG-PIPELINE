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
            
            foundation_model        = "anthropic.claude-3-haiku-20240307-v1:0"
            
            description             = "Enhanced RAG agent with conversational memory and multilingual document analysis"

            instruction = "You are an expert data analyst who extracts key insights from RAG-retrieved documents. Your goal: deliver clear, evidence-based, and complete answers using concise reasoning. Rules: 1. Document Format: Each chunk starts with '[Document: NAME | ...]' indicating its source. Use ALL relevant chunks from ANY document to answer the question. For comparisons, actively use information from multiple documents. 2. Data Synthesis: Consolidate all relevant information from matching chunks to form a comprehensive answer. For specs (numbers, lists, technical terms), prioritize explicit mentions. 3. Cite Sources: Always cite the document source when answering (e.g., 'From the Cherry document, the engine is...' or 'Hyundai offers...'). 4. Comparisons: When asked to compare items from different documents, extract information from BOTH documents and present a clear comparison. 5. Only reply 'no data found' if the concept is entirely missing from ALL documents. 6. For IMAGE REQUESTS: output ONLY the lines containing 'IMAGE_URL'. No text or explanation. 7. Keep answers concise, structured, and focused on evidence. Be fast, confident, and factual."

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

          resource "aws_bedrockagent_agent_alias" "production" {
            agent_id         = aws_bedrockagent_agent.rag_agent.agent_id
            agent_alias_name = "production"
            description      = "Production alias for RAG agent"

            depends_on = [null_resource.prepare_agent]
          }

          resource "time_sleep" "wait_for_agent_ready" {
            depends_on      = [null_resource.prepare_agent]
            create_duration = "60s"
          }

          # Production alias is created by null_resource.update_production_alias