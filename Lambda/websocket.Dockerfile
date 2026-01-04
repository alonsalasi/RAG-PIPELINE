FROM public.ecr.aws/lambda/python:3.11

# Copy requirements and install
COPY websocket_requirements.txt ${LAMBDA_TASK_ROOT}
RUN pip install --no-cache-dir -r websocket_requirements.txt

# Copy handler code
COPY websocket_handler.py ${LAMBDA_TASK_ROOT}

CMD ["websocket_handler.lambda_handler"]
