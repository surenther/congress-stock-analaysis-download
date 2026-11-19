FROM python:3.11-slim

WORKDIR /app

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OUTPUT_BASE_DIR=/data

# curl is included for the container healthcheck. No OCR system binaries are
# required anymore: document text is extracted with pure-Python libraries and
# the domain extraction is delegated to the LiteLLM Proxy.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY extraction_engine.py app.py auth_utils.py ./

# Create default storage mount point for external host storage
RUN mkdir -p /data

EXPOSE 8513

# Default command: Launch FastAPI microservice
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8513"]
