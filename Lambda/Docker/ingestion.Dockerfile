# ============================================================
# 🏗️ Stage 1 — Build Tesseract & Python dependencies
# ============================================================
FROM amazonlinux:2023 AS builder

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONPATH=/var/task \
    LD_LIBRARY_PATH=/usr/local/lib64:/usr/local/lib

WORKDIR /tmp

# ------------------------------------------------------------
# 1️⃣ Install build-time dependencies
# ------------------------------------------------------------
RUN dnf -y update --allowerasing && \
    dnf -y groupinstall "Development Tools" --allowerasing && \
    dnf -y install --allowerasing \
        python3.11 python3.11-pip python3.11-devel \
        wget git tar bzip2 bzip2-devel \
        poppler-utils ghostscript \
        libjpeg-turbo-devel libpng-devel zlib-devel \
        libtiff-devel libwebp-devel \
        icu libicu-devel \
        libarchive libarchive-devel \
        curl curl-devel \
        cmake automake autoconf libtool pkgconfig m4 && \
    dnf clean all

# ------------------------------------------------------------
# 2️⃣ Build Leptonica 1.83.1
# ------------------------------------------------------------
RUN wget -q https://github.com/DanBloomberg/leptonica/archive/refs/tags/1.83.1.tar.gz && \
    tar -xzf 1.83.1.tar.gz && \
    cd leptonica-1.83.1 && \
    autoreconf -ivf && \
    ./configure && \
    make -j"$(nproc)" && make install && ldconfig && \
    cd /tmp && rm -rf leptonica-*

# ------------------------------------------------------------
# 3️⃣ Build Tesseract 5.3 (minimal build)
# ------------------------------------------------------------
RUN git clone https://github.com/tesseract-ocr/tesseract.git && \
    cd tesseract && git checkout 5.3.0 && \
    mkdir build && cd build && \
    cmake .. \
        -DLeptonica_DIR=/usr/local/lib/cmake/Leptonica \
        -DCMAKE_PREFIX_PATH=/usr/local \
        -DCMAKE_INSTALL_PREFIX=/usr/local \
        -DBUILD_TRAINING_TOOLS=OFF \
        -DGRAPHICS_DISABLED=ON \
        -DOPENMP_BUILD=OFF && \
    make -j"$(nproc)" && make install && ldconfig && \
    cd /tmp && rm -rf tesseract

# ------------------------------------------------------------
# 4️⃣ Install Tesseract Language Data (tessdata)
# ------------------------------------------------------------
RUN mkdir -p /usr/local/share/tessdata && \
    wget -q https://github.com/tesseract-ocr/tessdata_fast/raw/main/eng.traineddata -O /usr/local/share/tessdata/eng.traineddata && \
    wget -q https://github.com/tesseract-ocr/tessdata_fast/raw/main/heb.traineddata -O /usr/local/share/tessdata/heb.traineddata

# ------------------------------------------------------------
# 5️⃣ Install Python dependencies and AWS Runtime Client
# ------------------------------------------------------------
COPY ingestion_requirements.txt /tmp/
RUN python3.11 -m pip install --upgrade pip && \
    python3.11 -m pip install --no-cache-dir -r ingestion_requirements.txt -t /var/task/ && \
    # CRITICAL FIX: Install the AWS Lambda Runtime Interface Client
    python3.11 -m pip install awslambdaric -t /var/task/ && \
    find /var/task -type d -name "__pycache__" -exec rm -rf {} +


# ============================================================
# 🪶 Stage 2 — Runtime (Lambda-friendly, no strip)
# ============================================================
FROM amazonlinux:2023

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONPATH=/var/task \
    LD_LIBRARY_PATH=/usr/local/lib64:/usr/local/lib \
    TESSDATA_PREFIX=/usr/local/share/tessdata

WORKDIR /var/task # Standard Lambda working directory

# ------------------------------------------------------------
# 6️⃣ Runtime dependencies only (very light)
# ------------------------------------------------------------
RUN dnf -y install --allowerasing \
        python3.11 python3.11-pip \
        libjpeg-turbo libpng zlib \
        libtiff libwebp icu libarchive \
        poppler-utils ghostscript && \
    dnf clean all && rm -rf /var/cache/dnf/*

# ------------------------------------------------------------
# 7️⃣ Copy binaries and Python packages
# ------------------------------------------------------------
COPY --from=builder /usr/local /usr/local
COPY --from=builder /var/task /var/task

# ------------------------------------------------------------
# 8️⃣ Copy your application code
# ------------------------------------------------------------
COPY worker.py /var/task/
COPY lambda_ingest_handler.py /var/task/

# ------------------------------------------------------------
# 9️⃣ Link tesseract binary and basic cleanup
# ------------------------------------------------------------
RUN ln -sf /usr/local/bin/tesseract /usr/bin/tesseract && \
    rm -rf /usr/share/man /usr/share/doc /usr/share/locale

# ------------------------------------------------------------
# 🔟 Verify installation
# ------------------------------------------------------------
RUN tesseract --version && tesseract --list-langs

# ------------------------------------------------------------
# 1️⃣1️⃣ Lambda-compatible entrypoint (FINAL FIX: Runtime.InvalidEntrypoint/awslambdaric)
# ------------------------------------------------------------
# Explicitly use python to run the Lambda Runtime Interface Client (RIC)
CMD ["/usr/bin/python3.11", "-m", "awslambdaric", "lambda_ingest_handler.lambda_handler"]