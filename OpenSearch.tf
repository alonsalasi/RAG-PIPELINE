resource "aws_opensearch_domain" "vector_search" {
  domain_name           = "${var.project_name}-os"
  engine_version        = "OpenSearch_2.11"

  cluster_config {
    instance_type = var.opensearch_instance_type
    instance_count = 1
  }

  vpc_options {
    subnet_ids         = aws_subnet.private.*.id
    security_group_ids = [aws_security_group.opensearch_sg.id]
  }

  ebs_options {
    ebs_enabled = true
    volume_size = 10
    volume_type = "gp3"
  }

  domain_endpoint_options {
    enforce_https = true
    tls_security_policy = "Policy-MinTLS12-2019-07"
  }

  node_to_node_encryption {
    enabled = true
  }

  encrypt_at_rest {
    enabled = true
  }

  access_policies = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Principal = {
          AWS = "*"
        },
        Action = "es:*",
        Resource = "arn:aws:es:${var.aws_region}:${data.aws_caller_identity.current.account_id}:domain/${aws_opensearch_domain.vector_search.domain_name}/*"
        Condition = {
          IpAddress = {
            aws:SourceIp [
              aws_vpc.main.cidr_block
            ]
          }
        }
      }
    ]
  })
}

data "aws_caller_identity" "current" {}
