FROM python:3.11-slim

WORKDIR /app

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OUTPUT_BASE_DIR=/data

# Install curl for container healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
# NOTE: No .env files are copied into the image. The .env.house / .env.senate
# files are provided at runtime via docker-compose volume mounts and must be
# created manually on the host (see README).
COPY download_filings.py app.py ./

# Create default storage mount point for external host storage
RUN mkdir -p /data

EXPOSE 8511

# Default command: Launch FastAPI microservice
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8511"]
