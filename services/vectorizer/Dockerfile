FROM python:3.11-slim

WORKDIR /app

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OUTPUT_BASE_DIR=/data

# curl is included for the container healthcheck. No OCR/PDF system binaries are
# required: this service only reads the standardized JSON produced by the parser
# and delegates embedding generation to the LiteLLM Proxy.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY app.py auth_utils.py chunker.py embedder.py db_init.py ./

# Create default storage mount point for external host storage
RUN mkdir -p /data

# Run as a non-root user (least privilege). The mounted host volume must be
# readable by this UID (10001).
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app /data
USER appuser

EXPOSE 8514

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8514/health || exit 1

# Default command: Launch FastAPI microservice
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8514"]
