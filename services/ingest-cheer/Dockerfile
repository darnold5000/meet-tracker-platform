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

# Fail the build if this file is missing from the Cloud Build upload (gcloudignore, etc.).
COPY cheer_ingest_main.py /app/cheer_ingest_main.py

# Copy project
COPY . /app

# Default: cheer-only Varsity score sync (no MSO / gymnastics ingest.py).
# Entrypoint lives at repo root (same pattern as ingest.py) so Cloud Run args stay simple.
# Override command to run legacy gym pipeline: python,ingest.py,--scrape-limit,1,--use-target-meets
CMD ["python", "cheer_ingest_main.py"]

