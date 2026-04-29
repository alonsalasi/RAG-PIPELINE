# Lambda Security Group - Tightened for HTTPS only
resource "aws_security_group" "lambda_sg" {
  count       = var.enable_lambda_vpc ? 1 : 0
  name        = "${var.project_name}-lambda-sg"
  description = "Security group for Lambda functions - HTTPS egress only"
  vpc_id      = aws_vpc.main[0].id

  # Ingress - Allow traffic from itself and VPC CIDR for VPC endpoints
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    self        = true
    description = "Allow HTTPS from Lambda to VPC endpoints"
  }

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.main[0].cidr_block]
    description = "Allow HTTPS from VPC CIDR to VPC endpoints (required for CloudWatch Logs)"
  }

  # Egress - HTTPS only to AWS services
  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTPS to AWS services (Bedrock, S3, etc)"
  }

  tags = {
    Name = "${var.project_name}-lambda-sg"
  }
}