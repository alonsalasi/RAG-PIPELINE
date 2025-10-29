# Lambda Security Group - Tightened for HTTPS only
resource "aws_security_group" "lambda_sg" {
  name        = "${var.project_name}-lambda-sg"
  description = "Security group for Lambda functions - HTTPS egress only"
  vpc_id      = aws_vpc.main.id

  # No ingress - Lambda doesn't need inbound connections

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