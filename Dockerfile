# ── Production Dockerfile ──────────────────────────────────
# Designed for Google Cloud Run Jobs (serverless batch execution).
# The container runs the pipeline ONCE and exits.
# Cloud Scheduler handles the 15-day timing externally.

FROM python:3.10-slim

# Prevent Python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install git (needed to push updated dashboard files back to GitHub)
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run the pipeline once and exit (Cloud Scheduler triggers the next run)
CMD ["python", "main.py", "--source", "live"]
