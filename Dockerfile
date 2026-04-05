FROM python:3.12-slim

WORKDIR /app

# System dependencies for Playwright
RUN apt-get update && apt-get install -y \
    wget curl gnupg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY dashboard/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright + webkit with all system deps
RUN playwright install chromium --with-deps

# Copy TikTokApi package (crawler imports it)
COPY TikTokApi/ ./TikTokApi/

# Copy dashboard code
COPY dashboard/ ./dashboard/

# Data directory — Railway volume mounts here
RUN mkdir -p /data

ENV DATA_DIR=/data
ENV TIKTOK_BROWSER=chromium
ENV PYTHONUNBUFFERED=1

WORKDIR /app/dashboard

EXPOSE 8080

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}"]
