# syntax=docker/dockerfile:1.4
# ==========================================================
# Stage 1 — Builder: install Python deps with cache
# ==========================================================
FROM public.ecr.aws/lambda/python:3.11 AS builder

# Use BuildKit cache for pip downloads to speed up rebuilds
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir \
        boto3>=1.34.127 \
        numpy==1.26.4 \
        faiss-cpu==1.9.0 \
        langchain==0.2.14 \
        langchain-community==0.2.12 \
        langchain-aws==0.1.8 \
        pdf2image==1.17.0 \
        pillow==11.0.0 \
        pytesseract==0.3.10

# ==========================================================
# Stage 2 — Runtime: lightweight Lambda environment
# ==========================================================
FROM public.ecr.aws/lambda/python:3.11

# Copy installed dependencies from builder
COPY --from=builder /var/lang/lib/python3.11/site-packages ${LAMBDA_TASK_ROOT}

# Copy your Lambda handler and supporting code
COPY lambda_api_handler.py worker.py ${LAMBDA_TASK_ROOT}/

# Optional environment tuning
ENV PYTHONUNBUFFERED=1

# Lambda entrypoint
CMD ["lambda_api_handler.lambda_handler"]
