FROM python:3.11-slim

WORKDIR /app

# Install FFmpeg and dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Verify FFmpeg
RUN ffmpeg -version

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create temp directory
RUN mkdir -p /tmp && chmod 777 /tmp

# Expose port
EXPOSE 10000

# Run with increased timeout and better worker management
CMD gunicorn --bind 0.0.0.0:$PORT \
    --workers 1 \
    --threads 2 \
    --timeout 600 \
    --graceful-timeout 600 \
    --keep-alive 5 \
    --max-requests 100 \
    --max-requests-jitter 10 \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    app:app
