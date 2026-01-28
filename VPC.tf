resource "aws_vpc" "main" {
  count                = var.enable_lambda_vpc ? 1 : 0
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name        = "${var.project_name}-vpc"
    Environment = var.environment
    ManagedBy   = "terraform"
  }

  lifecycle {
    prevent_destroy = true
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

# Private Subnets
resource "aws_subnet" "private" {
  count             = var.enable_lambda_vpc ? 2 : 0
  vpc_id            = aws_vpc.main[0].id
  cidr_block        = "10.0.${count.index + 10}.0/24"
  availability_zone = data.aws_availability_zones.available.names[count.index]

  tags = {
    Name = "${var.project_name}-private-subnet-${count.index + 1}"
  }
}

# Private Route Table - No internet access, only VPC endpoints
resource "aws_route_table" "private" {
  count  = var.enable_lambda_vpc ? 2 : 0
  vpc_id = aws_vpc.main[0].id

  tags = {
    Name = "${var.project_name}-private-rt-${count.index + 1}"
  }
}

resource "aws_route_table_association" "private" {
  count          = var.enable_lambda_vpc ? 2 : 0
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}

# S3 Gateway Endpoint (FREE)
resource "aws_vpc_endpoint" "s3_gateway" {
  count             = var.enable_lambda_vpc ? 1 : 0
  vpc_id            = aws_vpc.main[0].id
  service_name      = "com.amazonaws.${data.aws_region.current.id}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = aws_route_table.private[*].id

  tags = {
    Name = "${var.project_name}-s3-endpoint"
  }

  lifecycle {
    create_before_destroy = true
  }
}

# VPC Endpoints for AWS Services
resource "aws_vpc_endpoint" "bedrock_runtime" {
  count               = var.enable_lambda_vpc ? 1 : 0
  vpc_id              = aws_vpc.main[0].id
  service_name        = "com.amazonaws.${data.aws_region.current.id}.bedrock-runtime"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.lambda_sg[0].id]
  private_dns_enabled = true

  tags = {
    Name = "${var.project_name}-bedrock-runtime-endpoint"
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_endpoint" "bedrock_agent_runtime" {
  count               = var.enable_lambda_vpc ? 1 : 0
  vpc_id              = aws_vpc.main[0].id
  service_name        = "com.amazonaws.${data.aws_region.current.id}.bedrock-agent-runtime"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.lambda_sg[0].id]
  private_dns_enabled = true

  tags = {
    Name = "${var.project_name}-bedrock-agent-runtime-endpoint"
  }
}

resource "aws_vpc_endpoint" "sqs" {
  count               = var.enable_lambda_vpc ? 1 : 0
  vpc_id              = aws_vpc.main[0].id
  service_name        = "com.amazonaws.${data.aws_region.current.id}.sqs"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.lambda_sg[0].id]
  private_dns_enabled = true

  tags = {
    Name = "${var.project_name}-sqs-endpoint"
  }
}

resource "aws_vpc_endpoint" "sns" {
  count               = var.enable_lambda_vpc ? 1 : 0
  vpc_id              = aws_vpc.main[0].id
  service_name        = "com.amazonaws.${data.aws_region.current.id}.sns"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.lambda_sg[0].id]
  private_dns_enabled = true

  tags = {
    Name = "${var.project_name}-sns-endpoint"
  }
}

resource "aws_vpc_endpoint" "kms" {
  count               = var.enable_lambda_vpc ? 1 : 0
  vpc_id              = aws_vpc.main[0].id
  service_name        = "com.amazonaws.${data.aws_region.current.id}.kms"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.lambda_sg[0].id]
  private_dns_enabled = true

  tags = {
    Name = "${var.project_name}-kms-endpoint"
  }
}

resource "aws_vpc_endpoint" "logs" {
  count               = var.enable_lambda_vpc ? 1 : 0
  vpc_id              = aws_vpc.main[0].id
  service_name        = "com.amazonaws.${data.aws_region.current.id}.logs"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.lambda_sg[0].id]
  private_dns_enabled = true

  tags = {
    Name = "${var.project_name}-logs-endpoint"
  }
}

resource "aws_vpc_endpoint" "lambda" {
  count               = var.enable_lambda_vpc ? 1 : 0
  vpc_id              = aws_vpc.main[0].id
  service_name        = "com.amazonaws.${data.aws_region.current.id}.lambda"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.lambda_sg[0].id]
  private_dns_enabled = true

  tags = {
    Name = "${var.project_name}-lambda-endpoint"
  }
}

