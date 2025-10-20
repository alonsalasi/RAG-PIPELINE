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

variable "rds_username" {
  description = "Master username for the RDS PostgreSQL instance"
  type        = string
  default     = "dbmaster"
}

variable "rds_password" {
  description = "Master password for the RDS PostgreSQL instance (In production, use Secrets Manager)"
  type        = string
  sensitive   = true
}

variable "environment" {
  description = "Project Enviroment"
  type        = string
  default     = "default"
}

variable "opensearch_instance_type" {
  description = "The instance type for the OpenSearch data nodes"
  type        = string
  default     = "t3.small.search"
}

variable "ecs_task_cpu" {
  description = "The CPU limit (in vCPU units) for the Fargate task"
  type        = number
  default     = 0.5 # 512 is 0.5 vCPU
}

variable "ecs_task_memory" {
  description = "The memory limit (in GB) for the Fargate task"
  type        = number
  default     = 1 # 1GB
}
