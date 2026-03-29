# Dockerfile
#
# Custom Airflow image with ISR scraper dependencies.
#
# Build:
#   docker compose build
#
# Why a custom image instead of pip install at startup?
#   - Dependencies are baked in — container starts instantly
#   - Reproducible — same image every time
#   - Production pattern — you always know exactly what's in the container

FROM apache/airflow:2.9.0

# Switch to root to install system dependencies
USER root

# Install Playwright system dependencies (Chromium needs these)
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxcb1 \
    libxkbcommon0 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Switch back to airflow user for pip installs
USER airflow

# Copy and install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Also install psycopg3 (not in requirements.txt — added in Step 2)
RUN pip install --no-cache-dir "psycopg[binary]" psycopg-pool

# Install Playwright browsers (Chromium only — we don't need Firefox/WebKit)
RUN playwright install chromium