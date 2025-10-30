# warmup.tf - Keep Lambda warm with EventBridge

resource "aws_cloudwatch_event_rule" "lambda_warmup" {
  name                = "${var.project_name}-lambda-warmup"
  description         = "Trigger Lambda every 10 minutes to keep it warm"
  schedule_expression = "rate(10 minutes)"
}

resource "aws_cloudwatch_event_target" "lambda_warmup_target" {
  rule      = aws_cloudwatch_event_rule.lambda_warmup.name
  target_id = "LambdaWarmup"
  arn       = aws_lambda_function.agent_executor.arn
}

resource "aws_lambda_permission" "allow_eventbridge_warmup" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.agent_executor.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.lambda_warmup.arn
}
