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

@app.route('/')
def home():
    return jsonify({
        "service": "FFmpeg Video Creation API",
        "status": "running",
        "ffmpeg_available": os.path.exists(FFMPEG_PATH),
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
    if not os.path.exists(FFMPEG_PATH):
        return jsonify({
            "status": "error",
            "message": "FFmpeg not found"
        }), 404
    
    try:
        result = subprocess.run([FFMPEG_PATH, '-version'], capture_output=True, text=True, timeout=5)
        return jsonify({
            "status": "success",
            "version": result.stdout.split('\n')[0]
        }), 200
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/create-video', methods=['POST'])
def create_video():
    try:
        logger.info("Create video request received")
        unique_id = str(uuid.uuid4())[:8]
        audio_path = None
        image_path = None
        
        if request.is_json:
            data = request.get_json()
            
            if 'image' in data and 'audio' in data:
                logger.info("Processing base64 data")
                
                image_base64 = data['image']
                audio_base64 = data['audio']
                
                if 'base64,' in image_base64:
                    image_base64 = image_base64.split('base64,')[1]
                if 'base64,' in audio_base64:
                    audio_base64 = audio_base64.split('base64,')[1]
                
                try:
                    image_data = base64.b64decode(image_base64)
                    audio_data = base64.b64decode(audio_base64)
                except Exception as e:
                    return jsonify({"error": f"Base64 decode error: {str(e)}"}), 400
                
                image_path = os.path.join(TEMP_DIR, f'image_{unique_id}.jpg')
                audio_path = os.path.join(TEMP_DIR, f'audio_{unique_id}.mp3')
                
                with open(image_path, 'wb') as f:
                    f.write(image_data)
                with open(audio_path, 'wb') as f:
                    f.write(audio_data)
                
                output_filename = data.get('output_filename', 'output_video.mp4')
            
            elif 'audio_url' in data and 'image_url' in data:
                logger.info("Processing URL data")
                audio_url = data['audio_url']
                image_url = data['image_url']
                output_filename = data.get('output_filename', 'output_video.mp4')
                
                audio_path = os.path.join(TEMP_DIR, f'audio_{unique_id}.mp3')
                image_path = os.path.join(TEMP_DIR, f'image_{unique_id}.jpg')
                
                try:
                    audio_response = requests.get(audio_url, timeout=60)
                    audio_response.raise_for_status()
                    with open(audio_path, 'wb') as f:
                        f.write(audio_response.content)
                except Exception as e:
                    return jsonify({"error": f"Failed to download audio: {str(e)}"}), 400
                
                try:
                    image_response = requests.get(image_url, timeout=60)
                    image_response.raise_for_status()
                    with open(image_path, 'wb') as f:
                        f.write(image_response.content)
                except Exception as e:
                    if audio_path and os.path.exists(audio_path):
                        os.remove(audio_path)
                    return jsonify({"error": f"Failed to download image: {str(e)}"}), 400
            else:
                return jsonify({"error": "Invalid JSON. Provide base64 or URLs"}), 400
        
        elif 'audio' in request.files and 'image' in request.files:
            audio_file = request.files['audio']
            image_file = request.files['image']
            output_filename = request.form.get('output_filename', 'output_video.mp4')
            
            audio_path = os.path.join(TEMP_DIR, f'audio_{unique_id}_{secure_filename(audio_file.filename)}')
            image_path = os.path.join(TEMP_DIR, f'image_{unique_id}_{secure_filename(image_file.filename)}')
            
            audio_file.save(audio_path)
            image_file.save(image_path)
        else:
            return jsonify({"error": "Invalid input"}), 400
        
        if not os.path.exists(audio_path) or not os.path.exists(image_path):
            return jsonify({"error": "Failed to save input files"}), 500
        
        output_path = os.path.join(TEMP_DIR, f'video_{unique_id}_{output_filename}')
        
        cmd = [
            FFMPEG_PATH,
            '-loop', '1',
            '-i', image_path,
            '-i', audio_path,
            '-c:v', 'libx264',
            '-tune', 'stillimage',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-pix_fmt', 'yuv420p',
            '-shortest',
            '-y',
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        try:
            if os.path.exists(audio_path):
                os.remove(audio_path)
            if os.path.exists(image_path):
                os.remove(image_path)
        except:
            pass
        
        if result.returncode != 0:
            return jsonify({
                "error": "FFmpeg failed",
                "details": result.stderr
            }), 500
        
        if not os.path.exists(output_path):
            return jsonify({"error": "Video file was not created"}), 500
        
        file_size = os.path.getsize(output_path)
        
        return jsonify({
            "message": "Video created successfully",
            "video_url": f"/download/{os.path.basename(output_path)}",
            "filename": os.path.basename(output_path),
            "size": file_size
        }), 200
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/download/<filename>')
def download_file(filename):
    try:
        filepath = os.path.join(TEMP_DIR, filename)
        if os.path.exists(filepath):
            return send_file(filepath, as_attachment=True, download_name=filename, mimetype='video/mp4')
        return jsonify({"error": "File not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
