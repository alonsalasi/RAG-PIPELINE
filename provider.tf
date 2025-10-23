terraform {
  backend "s3" {
    bucket         = "pdfquery-tf-state-us-west-2" # REPLACE with actual bucket name pattern
    key            = "dev/infrastructure.tfstate"
    region         = "us-west-2"                         # REPLACE with your chosen region
    encrypt        = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}
