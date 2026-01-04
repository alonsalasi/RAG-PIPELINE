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

resource "aws_internet_gateway" "gw" {
  count  = var.enable_lambda_vpc ? 1 : 0
  vpc_id = aws_vpc.main[0].id
  tags = {
    Name = "${var.project_name}-igw"
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

# Public Subnets
resource "aws_subnet" "public" {
  count                   = var.enable_lambda_vpc ? 2 : 0
  vpc_id                  = aws_vpc.main[0].id
  cidr_block              = "10.0.${count.index + 1}.0/24"
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.project_name}-public-subnet-${count.index + 1}"
  }
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

# NAT Gateway - Required for WebSocket API responses (only 1 needed)
resource "aws_eip" "nat" {
  count  = var.enable_lambda_vpc ? 1 : 0
  domain = "vpc"

  tags = {
    Name = "${var.project_name}-nat-eip"
  }
}

resource "aws_nat_gateway" "main" {
  count         = var.enable_lambda_vpc ? 1 : 0
  allocation_id = aws_eip.nat[0].id
  subnet_id     = aws_subnet.public[0].id

  tags = {
    Name = "${var.project_name}-nat-gw"
  }

  depends_on = [aws_internet_gateway.gw]
}

# Public Route Table
resource "aws_route_table" "public" {
  count  = var.enable_lambda_vpc ? 1 : 0
  vpc_id = aws_vpc.main[0].id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.gw[0].id
  }

  tags = {
    Name = "${var.project_name}-public-rt"
  }
}

resource "aws_route_table_association" "public" {
  count          = var.enable_lambda_vpc ? 2 : 0
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public[0].id
}

# Private Route Table - Routes internet traffic through NAT Gateway
resource "aws_route_table" "private" {
  count  = var.enable_lambda_vpc ? 2 : 0
  vpc_id = aws_vpc.main[0].id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main[0].id
  }

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
  service_name      = "com.amazonaws.${data.aws_region.current.name}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = concat([aws_route_table.public[0].id], aws_route_table.private[*].id)

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
  service_name        = "com.amazonaws.${data.aws_region.current.name}.bedrock-runtime"
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
  service_name        = "com.amazonaws.${data.aws_region.current.name}.bedrock-agent-runtime"
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
  service_name        = "com.amazonaws.${data.aws_region.current.name}.sqs"
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
  service_name        = "com.amazonaws.${data.aws_region.current.name}.sns"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.lambda_sg[0].id]
  private_dns_enabled = true

  tags = {
    Name = "${var.project_name}-sns-endpoint"
  }
}

resource "aws_vpc_endpoint" "secretsmanager" {
  count               = var.enable_lambda_vpc ? 1 : 0
  vpc_id              = aws_vpc.main[0].id
  service_name        = "com.amazonaws.${data.aws_region.current.name}.secretsmanager"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.lambda_sg[0].id]
  private_dns_enabled = true

  tags = {
    Name = "${var.project_name}-secretsmanager-endpoint"
  }
}

resource "aws_vpc_endpoint" "kms" {
  count               = var.enable_lambda_vpc ? 1 : 0
  vpc_id              = aws_vpc.main[0].id
  service_name        = "com.amazonaws.${data.aws_region.current.name}.kms"
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
  service_name        = "com.amazonaws.${data.aws_region.current.name}.logs"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.lambda_sg[0].id]
  private_dns_enabled = true

  tags = {
    Name = "${var.project_name}-logs-endpoint"
  }
}

