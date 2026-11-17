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

# Copy application source code and configuration template
# NOTE: .env.house / .env.senate are NOT committed to git. They are mounted
# as volumes at runtime (see docker-compose.yml) and created by the CI workflow
# from repository secrets.
COPY download_filings.py app.py .env.example ./

# Create default storage mount point for external host storage
RUN mkdir -p /data

EXPOSE 8511

# Default command: Launch FastAPI microservice
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8511"]
