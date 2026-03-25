# Use a lightweight Python base image optimized for production
FROM python:3.10-slim

# Prevent memory buffering for Python logs
ENV PYTHONUNBUFFERED=1

# Set the working directory
WORKDIR /app

# Install dependencies first (leverages Docker cache for faster rebuilds)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Set default command to run the infinite scheduler daemon
CMD ["python", "scheduler.py"]
