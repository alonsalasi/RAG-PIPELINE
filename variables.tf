variable "aws_region" {
  description = "The AWS region to deploy the infrastructure"
  type        = string
  default     = "us-west-2"
}

variable "project_name" {
  description = "A unique prefix for all resources"
  type        = string
  default     = "rag-ecs-project"
}

variable "environment" {
  description = "Project Enviroment"
  type        = string
  default     = "default"
}

variable "api_version" {
  description = "Lambda_API_Version"
  type = number
  default = 1
}

variable "ingestion_image_tag" {
  description = "Docker image tag for ingestion Lambda (e.g., 'latest')."
  type        = string
  default     = "latest"
}

variable "ingestion_version" {
  description = "Lambda_Ingestion_Version"
  type = number
  default = 1
}

variable "layer_version" {
  description = "Lambda_Layer_Version"
  type = number
  default = 1
}