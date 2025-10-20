
output "rds_host" {
  description = "The hostname for the PostgreSQL database"
  value       = aws_db_instance.postgres.address
}

output "opensearch_endpoint" {
  description = "The HTTPS endpoint for the OpenSearch domain"
  value       = "https://${aws_opensearch_domain.vector_search.endpoint}"
}

output "ecs_cluster_name" {
  description = "The name of the ECS cluster"
  value       = aws_ecs_cluster.rag_cluster.name
}

output "terraform_state_bucket_name" {
  description = "The name of the S3 bucket storing the remote state"
  value       = aws_s3_bucket.terraform_state.bucket
}

output "rds_secret_arn" {
  description = "The ARN of the Secrets Manager secret storing RDS credentials"
  value       = aws_secretsmanager_secret.rds_master_credentials.arn
}

output "ecr_repository_url" {
  description = "The full URL for the RAG application ECR repository."
  value       = aws_ecr_repository.rag_repository.repository_url
}
