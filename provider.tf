terraform {
  # --- STEP 2: UNCOMMENT THIS BLOCK AFTER RUNNING THE INITIAL BOOTSTRAP ---
  # backend "s3" {
  #   bucket         = "rag-ecs-project-tf-state-us-west-2" # REPLACE with actual bucket name pattern
  #   key            = "dev/infrastructure.tfstate"
  #   region         = "us-west-2"                         # REPLACE with your chosen region
  #   dynamodb_table = "rag-ecs-project-tf-locks"          # REPLACE with actual table name pattern
  #   encrypt        = true
  # }
  # ------------------------------------------------------------------------

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
