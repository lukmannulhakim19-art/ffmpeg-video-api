FROM python:3.9-slim

# Install FFmpeg
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY app.py .

# Expose port
EXPOSE 8080

# Run app
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8080", "--timeout", "300", "--workers", "2"]
