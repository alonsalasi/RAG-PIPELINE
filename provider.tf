terraform {
  backend "s3" {
    bucket  = "pdfquery-tf-state-us-east-1"
    key     = "leidos/infrastructure.tfstate"
    region  = "us-east-1"
    profile = "default"
    encrypt = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.25"
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
