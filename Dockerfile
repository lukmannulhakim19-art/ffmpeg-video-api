# Use official Python image
FROM python:3.9-slim-bullseye

# Install FFmpeg and dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    libavcodec-extra \
    && rm -rf /var/lib/apt/lists/*

# Verify FFmpeg installation
RUN ffmpeg -version

# Set working directory
WORKDIR /app

# Copy requirements first (for caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app.py .

# Expose port
EXPOSE 8080

# Run with gunicorn
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8080", "--timeout", "300", "--workers", "2", "--access-logfile", "-", "--error-logfile", "-"]
```

---

## File 4 (Optional): `Procfile`
```
web: gunicorn app:app --bind 0.0.0.0:$PORT --timeout 300 --workers 2
```

---

## Struktur Folder di GitHub:
```
ffmpeg-video-api/
├── app.py
├── requirements.txt
├── Dockerfile
└── Procfile (optional)
```

---

## Cara Deploy:

1. **Upload semua file ke GitHub** (replace yang lama)
2. **Commit dengan message**: "Complete FFmpeg API with full path"
3. **Tunggu Railway auto-deploy** (2-3 menit)
4. **Test endpoint** di browser:
```
   https://ffmpeg-video-api-production-43ab.up.railway.app/test-ffmpeg
