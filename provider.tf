terraform {
  backend "s3" {
    bucket  = "pdfquery-tf-state-us-east-1"
    key     = "leidos/infrastructure.tfstate"
    region  = "us-east-1"
    profile = "leidos"
    encrypt = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.31"
    }
  }
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}
