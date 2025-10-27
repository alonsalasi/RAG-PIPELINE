# ==========================================================
# Multilingual OCR Ingestion Lambda (Tesseract + Textract)
# Debian slim + awslambdaric runtime shim
# ==========================================================
FROM python:3.11-slim-bookworm AS base

# 1) Install Lambda Runtime Interface Client (awslambdaric)
RUN pip install --no-cache-dir awslambdaric

# 2) System deps:
# - tesseract-ocr (engine)
# - poppler-utils (pdf2image)
# - ghostscript (some PDFs)
# - curl,wget (fetch tessdata)
# - libgl1, libglib2.0-0 (common deps for OCR/image libs)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        tesseract-ocr \
        poppler-utils \
        ghostscript \
        curl \
        wget \
        libgl1 \
        libglib2.0-0 && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# 3) Install English, Hebrew, and Turkish traineddata (best quality)
#    NOTE: we put them under /usr/share/tesseract-ocr/tessdata and set TESSDATA_PREFIX.
RUN mkdir -p /usr/share/tesseract-ocr/tessdata && \
    echo "Downloading tessdata files..." && \
    curl -L -o /usr/share/tesseract-ocr/tessdata/eng.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/eng.traineddata && \
    curl -L -o /usr/share/tesseract-ocr/tessdata/heb.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/heb.traineddata && \
    curl -L -o /usr/share/tesseract-ocr/tessdata/tur.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/tur.traineddata && \
    ls -lh /usr/share/tesseract-ocr/tessdata

# 4. Copy Python dependencies
COPY ingestion_requirements.txt /tmp/ingestion_requirements.txt

# 5. Install dependencies into Lambda task directory
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc g++ make libgl1 \
    && pip install --no-cache-dir -r /tmp/ingestion_requirements.txt -t /var/task \
    && apt-get remove -y gcc g++ make \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# 6) Copy function code
#    Your current handler file is ingestion.py (lambda_handler), plus worker.py.
COPY lambda_ingest_handler.py worker.py /var/task/

# 7) Environment variables
ENV PYTHONUNBUFFERED=1
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/tessdata
# If your code reads these, you can set sensible defaults:
# ENV AWS_REGION=us-west-2
# ENV S3_BUCKET=pdfquery-rag-documents-default

# 8) Lambda working directory
WORKDIR /var/task

# 9) Entrypoint for Lambda runtime
ENTRYPOINT ["python3", "-m", "awslambdaric"]
CMD ["ingestion.lambda_handler"]
