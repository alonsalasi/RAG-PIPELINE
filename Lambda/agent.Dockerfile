# Agent Executor Lambda Dockerfile
FROM public.ecr.aws/lambda/python:3.11

# Copy requirements and install Python dependencies
COPY agent_requirements.txt ${LAMBDA_TASK_ROOT}
RUN pip install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org --no-cache-dir -r agent_requirements.txt

# Copy agent executor code and document autofill modules
COPY agent_executor.py ${LAMBDA_TASK_ROOT}
COPY document_parser.py ${LAMBDA_TASK_ROOT}
COPY field_matcher.py ${LAMBDA_TASK_ROOT}
COPY document_filler.py ${LAMBDA_TASK_ROOT}

# Set the CMD to your handler
CMD ["agent_executor.lambda_handler"]