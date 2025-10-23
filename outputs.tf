output "terraform_state_bucket_name" {
  description = "The name of the S3 bucket storing the remote state"
  value       = aws_s3_bucket.terraform_state.bucket
}


output "cloudfront_domain_name" {
  description = "The publicly accessible HTTPS URL for the RAG chatbot GUI."
  value       = aws_cloudfront_distribution.rag_frontend_cdn.domain_name
}