# Agent Executor Lambda Dockerfile
FROM public.ecr.aws/lambda/python:3.11

# Copy requirements and install Python dependencies
COPY agent_requirements.txt ${LAMBDA_TASK_ROOT}
RUN pip install --no-cache-dir -r agent_requirements.txt

# Copy agent executor code
COPY agent_executor.py ${LAMBDA_TASK_ROOT}

# Set the CMD to your handler
CMD ["agent_executor.lambda_handler"]