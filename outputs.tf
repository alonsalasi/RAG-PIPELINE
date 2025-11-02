# outputs.tf - Terraform Outputs

output "bedrock_agent_id" {
  value       = aws_bedrockagent_agent.rag_agent.agent_id
  description = "Bedrock Agent ID"
}

output "agent_alias_lookup_command" {
  value       = "aws bedrock-agent list-agent-aliases --agent-id ${aws_bedrockagent_agent.rag_agent.agent_id} --profile ${var.aws_profile} --query 'agentAliasSummaries[?agentAliasName==`production`].agentAliasId' --output text"
  description = "Command to get the production alias ID"
}
