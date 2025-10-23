resource "aws_cloudfront_origin_access_identity" "oai" {
  comment = "OAI for RAG Frontend S3 Bucket Access"
}

resource "aws_s3_bucket_policy" "rag_documents_cloudfront_access" {
  bucket = aws_s3_bucket.rag_documents.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Sid       = "AllowCloudFrontS3Access",
        Effect    = "Allow",
        Principal = {
          AWS = aws_cloudfront_origin_access_identity.oai.iam_arn
        },
        Action = [
          "s3:GetObject"
        ],
        Resource = [
          aws_s3_bucket.rag_documents.arn,
          "${aws_s3_bucket.rag_documents.arn}/*"
        ]
      }
    ]
  })
}

resource "aws_cloudfront_distribution" "rag_frontend_cdn" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "CDN for RAG Static Frontend (index.html)"
  default_root_object = "index.html" 

  origin {
    domain_name = aws_s3_bucket.rag_documents.bucket_regional_domain_name
    origin_id   = aws_s3_bucket.rag_documents.id

    s3_origin_config {
      origin_access_identity = aws_cloudfront_origin_access_identity.oai.cloudfront_access_identity_path
    }
  }

  default_cache_behavior {
    target_origin_id           = aws_s3_bucket.rag_documents.id
    viewer_protocol_policy     = "redirect-to-https" # Forces HTTPS
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true

    forwarded_values {
      query_string = true
      cookies {
        forward = "none"
      }
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true 
  }
  
  depends_on = [
    aws_s3_bucket_policy.rag_documents_cloudfront_access,
    aws_cloudfront_origin_access_identity.oai
  ]
}