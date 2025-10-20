locals {
  rds_credentials = jsondecode(data.aws_secretsmanager_secret_version.rds_password_value.secret_string)
}

resource "aws_db_instance" "postgres" {
  allocated_storage      = 20
  storage_type           = "gp2"
  engine                 = "postgres"
  engine_version         = "15.2"
  instance_class         = "db.t3.micro"
  identifier             = "${var.project_name}-rds-instance"
  
  username               = local.rds_credentials.username
  password               = local.rds_credentials.password
  
  db_name                = "ragdb"
  parameter_group_name   = "default.postgres15"
  skip_final_snapshot    = true
  multi_az               = false
  publicly_accessible    = false
  vpc_security_group_ids = [aws_security_group.rds_sg.id]
  db_subnet_group_name   = aws_db_subnet_group.rds.name
}
