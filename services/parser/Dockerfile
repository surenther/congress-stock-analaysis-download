FROM python:3.11-slim

WORKDIR /app

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OUTPUT_BASE_DIR=/data

# Install system binaries required for PDF rendering and OCR:
#   - tesseract-ocr     : OCR engine (pytesseract backend)
#   - poppler-utils     : pdftoppm/pdfinfo used by pdf2image
#   - libtesseract-dev  : Tesseract development headers
# curl is included for the container healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        tesseract-ocr \
        poppler-utils \
        libtesseract-dev \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY parser_engine.py app.py auth_utils.py ./

# Create default storage mount point for external host storage
RUN mkdir -p /data

EXPOSE 8513

# Default command: Launch FastAPI microservice
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8513"]
