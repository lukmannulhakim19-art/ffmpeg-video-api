from flask import Flask, request, jsonify, send_file
import subprocess
import os
import uuid
import requests
import base64
import shutil
from werkzeug.utils import secure_filename
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

TEMP_DIR = '/tmp'
os.makedirs(TEMP_DIR, exist_ok=True)

FFMPEG_PATH = shutil.which('ffmpeg') or '/usr/bin/ffmpeg'
logger.info(f"FFmpeg path: {FFMPEG_PATH}")

if os.path.exists(FFMPEG_PATH):
    logger.info("FFmpeg found successfully")
else:
    logger.error(f"FFmpeg not found at {FFMPEG_PATH}")


def build_download_url(filename):
    domain = os.environ.get("RENDER_EXTERNAL_URL")
    if domain:
        return f"{domain}/download/{filename}"
    return f"/download/{filename}"


@app.route('/')
def home():
    return jsonify({
        "service": "FFmpeg Video Creation API",
        "status": "running",
        "ffmpeg_available": os.path.exists(FFMPEG_PATH),
        "download_base": os.environ.get("RENDER_EXTERNAL_URL"),
        "endpoints": {
            "/create-video": "POST - Create video",
            "/health": "GET - Health check",
            "/test-ffmpeg": "GET - Test FFmpeg"
        }
    }), 200


@app.route('/health')
def health():
    ffmpeg_ok = os.path.exists(FFMPEG_PATH)
    return jsonify({
        "status": "healthy" if ffmpeg_ok else "degraded",
        "ffmpeg": "available" if ffmpeg_ok else "missing"
    }), 200 if ffmpeg_ok else 503


@app.route('/test-ffmpeg')
def test_ffmpeg():
    try:
        result = subprocess.run([FFMPEG_PATH, '-version'], capture_output=True, text=True, timeout=5)
        logger.info("FFmpeg version output:")
        logger.info(result.stdout)
        return jsonify({"status": "success", "version": result.stdout.split("\n")[0]}), 200
    except Exception as e:
        logger.error(f"FFmpeg test failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/create-video', methods=['POST'])
def create_video():
    try:
        logger.info("======== NEW CREATE VIDEO REQUEST ========")

        unique_id = str(uuid.uuid4())[:8]
        audio_path = None
        image_path = None

        # --- READ JSON ---
        if request.is_json:
            data = request.get_json()
            logger.info("Received JSON payload")

            # BASE64 MODE ----------------------------
            if "image" in data and "audio" in data:
                logger.info("Mode: BASE64 INPUT")

                img64 = data["image"]
                aud64 = data["audio"]

                if "base64," in img64:
                    img64 = img64.split("base64,")[1]
                if "base64," in aud64:
                    aud64 = aud64.split("base64,")[1]

                try:
                    image_bytes = base64.b64decode(img64)
                    audio_bytes = base64.b64decode(aud64)
                except Exception as e:
                    logger.error(f"Base64 decode error: {e}")
                    return jsonify({"error": f"Base64 decode error: {e}"}), 400

                image_path = os.path.join(TEMP_DIR, f"image_{unique_id}.jpg")
                audio_path = os.path.join(TEMP_DIR, f"audio_{unique_id}.mp3")

                open(image_path, "wb").write(image_bytes)
                open(audio_path, "wb").write(audio_bytes)

                output_filename = data.get("output_filename", "output_video.mp4")

            # URL MODE ----------------------------
            elif "audio_url" in data and "image_url" in data:
                logger.info("Mode: URL DOWNLOAD")

                audio_url = data["audio_url"]
                image_url = data["image_url"]

                audio_path = os.path.join(TEMP_DIR, f"audio_{unique_id}.mp3")
                image_path = os.path.join(TEMP_DIR, f"image_{unique_id}.jpg")

                try:
                    logger.info(f"Downloading audio: {audio_url}")
                    r = requests.get(audio_url, timeout=60)
                    r.raise_for_status()
                    open(audio_path, "wb").write(r.content)
                except Exception as e:
                    logger.error(f"Failed to download audio: {e}")
                    return jsonify({"error": f"Failed to download audio: {e}"}), 400

                try:
                    logger.info(f"Downloading image: {image_url}")
                    r = requests.get(image_url, timeout=60)
                    r.raise_for_status()
                    open(image_path, "wb").write(r.content)
                except Exception as e:
                    if os.path.exists(audio_path): os.remove(audio_path)
                    logger.error(f"Failed to download image: {e}")
                    return jsonify({"error": f"Failed to download image: {e}"}), 400

                output_filename = data.get("output_filename", "output_video.mp4")

            else:
                return jsonify({"error": "Invalid JSON input"}), 400

        else:
            return jsonify({"error": "Expected JSON input"}), 400

        if not os.path.exists(audio_path) or not os.path.exists(image_path):
            return jsonify({"error": "Failed to prepare input files"}), 500

        # OUTPUT PATH --------------------------------
        output_path = os.path.join(TEMP_DIR, f"video_{unique_id}.mp4")
        logger.info(f"Output path: {output_path}")

        # RUN FFMPEG --------------------------------
        cmd = [
            FFMPEG_PATH,
            "-loop", "1",
            "-i", image_path,
            "-i", audio_path,
            "-c:v", "libx264",
            "-tune", "stillimage",
            "-c:a", "aac",
            "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-shortest",
            "-y",
            output_path
        ]

        logger.info("FFmpeg command:")
        logger.info(" ".join(cmd))

        result = subprocess.run(cmd, capture_output=True, text=True)

        logger.info("FFmpeg STDOUT:")
        logger.info(result.stdout)

        logger.info("FFmpeg STDERR:")
        logger.info(result.stderr)

        if result.returncode != 0:
            logger.error("FFmpeg failed")
            return jsonify({"error": "FFmpeg failed", "stderr": result.stderr}), 500

        if not os.path.exists(output_path):
            logger.error("Output video not created")
            return jsonify({"error": "Video file not created"}), 500

        # RENDER MAX FILE SIZE LIMIT CHECK
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        if size_mb > 95:
            logger.warning("Video too large for Render filesystem")
            os.remove(output_path)
            return jsonify({"error": "Video too large for Render (max 100 MB)"}), 400

        logger.info(f"Video created successfully: {output_path} ({size_mb:.2f} MB)")

        # OUTPUT RESULT ------------------------------
        filename = os.path.basename(output_path)
        download_url = build_download_url(filename)

        return jsonify({
            "message": "Video created successfully",
            "filename": filename,
            "video_url": download_url,
            "size_mb": size_mb
        }), 200

    except Exception as e:
        logger.error(f"Exception: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/download/<filename>')
def download_file(filename):
    try:
        filepath = os.path.join(TEMP_DIR, filename)
        if os.path.exists(filepath):
            return send_file(filepath, as_attachment=True, mimetype="video/mp4")
        return jsonify({"error": "File not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
