FROM mcr.microsoft.com/playwright/python:v1.54.0-jammy

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

