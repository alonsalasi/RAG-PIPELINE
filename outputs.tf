output "terraform_state_bucket_name" {
  description = "The name of the S3 bucket storing the remote state"
  value       = aws_s3_bucket.terraform_state.bucket
}


output "cloudfront_domain_name" {
  description = "The publicly accessible HTTPS URL for the RAG chatbot GUI."
  value       = aws_cloudfront_distribution.rag_frontend_cdn.domain_name
}

output "ingestion_lambda_ecr_repository_url" {
  description = "The URL of the ECR repository for the ingestion Lambda image."
  value       = aws_ecr_repository.ingestion_lambda_repo.repository_url
}

output "api_lambda_ecr_repository_url" {
  description = "The URL of the ECR repository for the api Lambda image."
  value       = aws_ecr_repository.api_lambda_repo.repository_url
}