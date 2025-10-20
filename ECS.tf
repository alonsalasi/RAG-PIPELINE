resource "aws_ecs_cluster" "rag_cluster" {
  name = "${var.project_name}-rag-cluster"
}

resource "aws_cloudwatch_log_group" "rag_logs" {
  name              = "/ecs/${var.project_name}-rag-app-logs"
  retention_in_days = 90 
  
  tags = {
    Name        = "${var.project_name}-rag-logs"
    Environment = var.environment
  }
}

resource "aws_ecs_task_definition" "rag_worker_task" {
  family                   = "${var.project_name}-rag-worker"
  cpu                      = "256"
  memory                   = "512"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  execution_role_arn       = aws_iam_role.ecs_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([
    {
      name    = "rag-worker"
      image   = "${aws_ecr_repository.rag_repository.repository_url}:latest"
      command = ["python", "worker.py"]
      environment = [
        {
          name  = "SQS_QUEUE_URL"
          value = aws_sqs_queue.rag_ingestion_queue.url 
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.rag_logs.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "worker"
        }
      }
    }
  ])
}

resource "aws_ecs_task_definition" "rag_api_task" {
  family                   = "${var.project_name}-rag-api"
  cpu                      = "512"
  memory                   = "1024"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  execution_role_arn       = aws_iam_role.ecs_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([
    {
      name    = "rag-api"
      image   = "${aws_ecr_repository.rag_repository.repository_url}:latest"
      command = ["gunicorn", "-w", "4", "-b", "0.0.0.0:80", "app:app"]
      portMappings = [
        {
          containerPort = 80
          hostPort      = 80
        }
      ]
      environment = [
        {
          name  = "VECTOR_DB_ENDPOINT"
          value = aws_opensearch_domain.vector_search.endpoint
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.rag_logs.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "api"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "rag_worker_service" {
  name            = "${var.project_name}-rag-worker-service"
  cluster         = aws_ecs_cluster.rag_cluster.id
  task_definition = aws_ecs_task_definition.rag_worker_task.arn
  launch_type     = "FARGATE"
  desired_count   = 1

  network_configuration {
    subnets          = aws_subnet.private.*.id
    security_groups  = [aws_security_group.ecs_sg.id]
    assign_public_ip = false
  }
}

resource "aws_ecs_service" "rag_api_service" {
  name            = "${var.project_name}-rag-api-service"
  cluster         = aws_ecs_cluster.rag_cluster.id
  task_definition = aws_ecs_task_definition.rag_api_task.arn
  launch_type     = "FARGATE"
  desired_count   = 2 

  network_configuration {
    subnets          = aws_subnet.private.*.id
    security_groups  = [aws_security_group.ecs_sg.id]
    assign_public_ip = false 
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.rag_api.arn
    container_name   = "rag-api"
    container_port   = 80
  }

  depends_on = [
    aws_lb_listener.http
  ]
}