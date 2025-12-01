# Use Python with FFmpeg support
FROM python:3.11-slim-bullseye

# Set working directory
WORKDIR /app

# Install FFmpeg and dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

# Verify FFmpeg installation
RUN ffmpeg -version

# Copy requirements first (for better caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create temp directory with proper permissions
RUN mkdir -p /tmp && chmod 777 /tmp

# Expose port
EXPOSE 8080

# Use shell form to allow environment variable expansion
CMD gunicorn --bind 0.0.0.0:${PORT:-8080} --timeout 300 --workers 2 --log-level info app:app
