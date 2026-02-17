# 🐍 Base image: lightweight Python 3.11 optimized for AWS Lambda
FROM python:3.11-slim-bookworm

# Install AWS Lambda Runtime Interface Client with trusted hosts
RUN pip install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org --no-cache-dir awslambdaric

# -----------------------------------------------------
# 🧰 System dependencies (OCR + PDF rendering)
# -----------------------------------------------------
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        tesseract-ocr poppler-utils curl libgl1-mesa-glx libglib2.0-0 && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# -----------------------------------------------------
# 🌍 Install Tesseract language data (English, Hebrew, Arabic, Turkish)
# -----------------------------------------------------
RUN mkdir -p /usr/share/tesseract-ocr/tessdata && \
    curl -k -L -o /usr/share/tesseract-ocr/tessdata/eng.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/eng.traineddata && \
    curl -k -L -o /usr/share/tesseract-ocr/tessdata/heb.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/heb.traineddata && \
    curl -k -L -o /usr/share/tesseract-ocr/tessdata/ara.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/ara.traineddata && \
    curl -k -L -o /usr/share/tesseract-ocr/tessdata/tur.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/tur.traineddata

# -----------------------------------------------------
# 🐍 Python dependencies (installed into Lambda /var/task)
# -----------------------------------------------------
COPY ingestion_requirements.txt /tmp/ingestion_requirements.txt

RUN pip install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org --no-cache-dir -r /tmp/ingestion_requirements.txt -t /var/task && \
    find /var/task -name "*.pyc" -delete && \
    find /var/task -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true && \
    find /var/task -name "*.so" -exec strip {} \; 2>/dev/null || true

# -----------------------------------------------------
# 🧠 Lambda Code
# -----------------------------------------------------
COPY lambda_ingest_handler.py worker.py semantic_chunker.py image_analysis.py office_converter.py document_parser.py /var/task/

# -----------------------------------------------------
# 🤖 MobileNet-SSD Model Files
# -----------------------------------------------------
RUN mkdir -p /opt/models
COPY models/deploy.prototxt /opt/models/deploy.prototxt
COPY models/mobilenet_iter_73000.caffemodel /opt/models/mobilenet_iter_73000.caffemodel

# -----------------------------------------------------
# ⚙️ Environment configuration
# -----------------------------------------------------
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TESSDATA_PREFIX=/usr/share/tesseract-ocr/tessdata \
    HOME=/tmp \
    XDG_CACHE_HOME=/tmp

WORKDIR /var/task

# -----------------------------------------------------
# 🚀 Lambda Runtime Entrypoint
# -----------------------------------------------------
ENTRYPOINT ["python3", "-m", "awslambdaric"]
CMD ["lambda_ingest_handler.lambda_handler"]
