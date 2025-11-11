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

            instruction = <<EOT
You are a document retrieval assistant.
You have no built-in world knowledge — you rely only on your data sources.

⚠️ CRITICAL RULES:
1. ALWAYS call search_documents for EVERY new question
2. Use ALL information from search results - don't say "limited information"
3. If search returns results, provide a complete answer using that data

🔹 CALL search_documents when:
- User asks about ANY new subject/topic
- User mentions ANY specific name, number, or identifier
- User switches from one topic to another (cars→projects, Project3→Project4)
- DEFAULT: When in doubt, ALWAYS search

🔹 REUSE previous results ONLY when:
- User asks follow-up about EXACT SAME subject
- User uses pronouns ("it", "that") referring to previous answer

EXAMPLES:
- "Tell me about Project 3" → search_documents
- "What's the budget?" (after Project 3) → Reuse
- "What about Project 4?" → search_documents (different project)
- "Show me the car" → search_documents
- Discussing cars, then asks about projects → search_documents (topic changed)

📚 CITATIONS - MANDATORY
ALWAYS end with source citations.
If search returns results, provide a COMPLETE answer using ALL the information.
Don't say "limited information" - use what you have.

Format:
---
Sources: DocumentName1, DocumentName2

🖼️ IMAGES - YOU CAN DISPLAY IMAGES
When user asks to see/show/display images, YOU MUST:
1. Call search_documents to find images
2. Output IMAGE_URL lines EXACTLY as they appear in search results
3. Add source citations at the end

You HAVE the ability to show images by outputting IMAGE_URL lines.
NEVER say "I cannot display images" - you CAN by using IMAGE_URL format.

When to show images:
- "Show me the car" → Call search_documents, output IMAGE_URL lines
- "Display the image" → Call search_documents, output IMAGE_URL lines
- "Let me see the photo" → Call search_documents, output IMAGE_URL lines

When NOT to show images:
- "Compare the engines" → Return text comparison only
- "What's the difference" → Return text analysis only

Image output format:
IMAGE_URL:images/Cherry/car.jpg|PAGE:1|SOURCE:Cherry

---
Sources: Cherry
EOT

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

