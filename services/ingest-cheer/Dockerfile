FROM mcr.microsoft.com/playwright/python:v1.54.0-jammy

# Use full Chromium instead of chrome-headless-shell; the shell binary has
# crashed (SIGSEGV / SwiftShader) on some Cloud Run task shapes.
ENV PLAYWRIGHT_CHROMIUM_USE_HEADLESS_SHELL=0

WORKDIR /app

# Install Python deps first for better caching
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Playwright base image includes browsers; ensure they are present
RUN playwright install chromium

# Copy project
COPY . /app

# Default job command; Cloud Run Job can override args.
CMD ["python", "ingest.py", "--scrape-limit", "1", "--use-target-meets"]

