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

# Setup logging to stdout (Railway needs this)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

TEMP_DIR = '/tmp'
os.makedirs(TEMP_DIR, exist_ok=True)

# Find FFmpeg executable
FFMPEG_PATH = shutil.which('ffmpeg') or '/usr/bin/ffmpeg'
logger.info(f"FFmpeg path: {FFMPEG_PATH}")

# Verify FFmpeg exists at startup
if not os.path.exists(FFMPEG_PATH):
    logger.error(f"CRITICAL: FFmpeg not found at {FFMPEG_PATH}")
    logger.error("Application will not work without FFmpeg!")
else:
    try:
        result = subprocess.run([FFMPEG_PATH, '-version'], capture_output=True, text=True, timeout=5)
        logger.info(f"FFmpeg version: {result.stdout.split('ffmpeg version')[1].split()[0] if 'ffmpeg version' in result.stdout else 'Unknown'}")
        logger.info("FFmpeg is ready!")
    except Exception as e:
        logger.error(f"FFmpeg test failed: {str(e)}")

@app.route('/')
def home():
    logger.info("Root endpoint accessed")
    return jsonify({
        "service": "FFmpeg Video Creation API",
        "status": "running",
        "ffmpeg_available": os.path.exists(FFMPEG_PATH),
        "endpoints": {
            "/create-video": "POST - Create video (supports URL, file upload, or base64)",
            "/health": "GET - Health check",
            "/test-ffmpeg": "GET - Test FFmpeg installation"
        }
    }), 200

@app.route('/health')
def health():
    """Health check endpoint for Railway"""
    logger.info("Health check accessed")
    ffmpeg_ok = os.path.exists(FFMPEG_PATH)
    status_code = 200 if ffmpeg_ok else 503
    
    return jsonify({
        "status": "healthy" if ffmpeg_ok else "degraded",
        "ffmpeg": "available" if ffmpeg_ok else "missing",
        "ffmpeg_path": FFMPEG_PATH if ffmpeg_ok else None
    }), status_code

@app.route('/test-ffmpeg')
def test_ffmpeg():
    """Test FFmpeg installation"""
    logger.info("FFmpeg test accessed")
    
    if not os.path.exists(FFMPEG_PATH):
        logger.error(f"FFmpeg not found at {FFMPEG_PATH}")
        return jsonify({
            "status": "error",
            "message": f"FFmpeg not found at {FFMPEG_PATH}",
            "checked_paths": ['/usr/bin/ffmpeg', '/usr/local/bin/ffmpeg', '/bin/ffmpeg']
        }), 404
    
    try:
        result = subprocess.run([FFMPEG_PATH, '-version'], capture_output=True, text=True, timeout=5)
        version_info = result.stdout.split('\n')[0] if result.stdout else "Unknown"
        logger.info(f"FFmpeg test successful: {version_info}")
        
        return jsonify({
            "status": "success",
            "ffmpeg_path": FFMPEG_PATH,
            "version": version_info,
            "full_output": result.stdout[:500]  # First 500 chars
        }), 200
    except Exception as e:
        logger.error(f"FFmpeg test error: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/create-video', methods=['POST'])
def create_video():
    try:
        logger.info("=== Create video request received ===")
        unique_id = str(uuid.uuid4())[:8]
        audio_path = None
        image_path = None
        
        # Check if request is JSON (base64 or URL)
        if request.is_json:
            data = request.get_json()
            logger.info(f"Processing JSON request with keys: {list(data.keys())}")
            
            # Handle base64 input
            if 'image' in data and 'audio' in data:
                logger.info("Processing base64 data...")
                
                # Get base64 strings
                image_base64 = data['image']
                audio_base64 = data['audio']
                
                # Remove data URI prefix if exists
                if 'base64,' in image_base64:
                    image_base64 = image_base64.split('base64,')[1]
                if 'base64,' in audio_base64:
                    audio_base64 = audio_base64.split('base64,')[1]
                
                # Decode base64
                try:
                    image_data = base64.b64decode(image_base64)
                    audio_data = base64.b64decode(audio_base64)
                    logger.info(f"Decoded - Image: {len(image_data)} bytes, Audio: {len(audio_data)} bytes")
                except Exception as e:
                    logger.error(f"Base64 decode error: {str(e)}")
                    return jsonify({"error": f"Base64 decode error: {str(e)}"}), 400
                
                # Save to files
                image_path = os.path.join(TEMP_DIR, f'image_{unique_id}.jpg')
                audio_path = os.path.join(TEMP_DIR, f'audio_{unique_id}.mp3')
                
                with open(image_path, 'wb') as f:
                    f.write(image_data)
                
                with open(audio_path, 'wb') as f:
                    f.write(audio_data)
                
                logger.info(f"Files saved - Image: {image_path}, Audio: {audio_path}")
                output_filename = data.get('output_filename', 'output_video.mp4')
            
            # Handle URL input
            elif 'audio_url' in data and 'image_url' in data:
                logger.info("Processing URL data...")
                audio_url = data['audio_url']
                image_url = data['image_url']
                output_filename = data.get('output_filename', 'output_video.mp4')
                
                audio_path = os.path.join(TEMP_DIR, f'audio_{unique_id}.mp3')
                image_path = os.path.join(TEMP_DIR, f'image_{unique_id}.jpg')
                
                # Download files
                logger.info(f"Downloading audio from {audio_url}")
                try:
                    audio_response = requests.get(audio_url, timeout=60)
                    audio_response.raise_for_status()
                    with open(audio_path, 'wb') as f:
                        f.write(audio_response.content)
                    logger.info(f"Audio downloaded: {len(audio_response.content)} bytes")
                except Exception as e:
                    logger.error(f"Audio download error: {str(e)}")
                    return jsonify({"error": f"Failed to download audio: {str(e)}"}), 400
                
                logger.info(f"Downloading image from {image_url}")
                try:
                    image_response = requests.get(image_url, timeout=60)
                    image_response.raise_for_status()
                    with open(image_path, 'wb') as f:
                        f.write(image_response.content)
                    logger.info(f"Image downloaded: {len(image_response.content)} bytes")
                except Exception as e:
                    logger.error(f"Image download error: {str(e)}")
                    if audio_path and os.path.exists(audio_path):
                        os.remove(audio_path)
                    return jsonify({"error": f"Failed to download image: {str(e)}"}), 400
            
            else:
                return jsonify({"error": "Invalid JSON input. Provide either base64 (image/audio) or URLs (audio_url/image_url)"}), 400
        
        # Handle multipart file upload
        elif 'audio' in request.files and 'image' in request.files:
            logger.info("Processing file upload...")
            audio_file = request.files['audio']
            image_file = request.files['image']
            output_filename = request.form.get('output_filename', 'output_video.mp4')
            
            audio_path = os.path.join(TEMP_DIR, f'audio_{unique_id}_{secure_filename(audio_file.filename)}')
            image_path = os.path.join(TEMP_DIR, f'image_{unique_id}_{secure_filename(image_file.filename)}')
            
            audio_file.save(audio_path)
            image_file.save(image_path)
            logger.info(f"Files uploaded - Image: {image_path}, Audio: {audio_path}")
        
        else:
            return jsonify({"error": "Invalid input. Provide either JSON (base64/URLs) or multipart files"}), 400
        
        # Validate files exist
        if not os.path.exists(audio_path) or not os.path.exists(image_path):
            logger.error("Input files not found after processing")
            return jsonify({"error": "Failed to save input files"}), 500
        
        # Verify file sizes
        audio_size = os.path.getsize(audio_path)
        image_size = os.path.getsize(image_path)
        logger.info(f"File sizes - Image: {image_size} bytes, Audio: {audio_size} bytes")
        
        if audio_size == 0 or image_size == 0:
            logger.error("One or more input files are empty")
            return jsonify({"error": "Input files are empty"}), 400
        
        # Create video with FFmpeg
        output_path = os.path.join(TEMP_DIR, f'video_{unique_id}_{output_filename}')
        
        logger.info(f"Creating video: {output_path}")
        logger.info(f"Using FFmpeg: {FFMPEG_PATH}")
        
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
        
        logger.info(f"FFmpeg command: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        # Cleanup input files
        try:
            if os.path.exists(audio_path):
                os.remove(audio_path)
            if os.path.exists(image_path):
                os.remove(image_path)
            logger.info("Input files cleaned up")
        except Exception as e:
            logger.warning(f"Cleanup error: {str(e)}")
        
        if result.returncode != 0:
            logger.error(f"FFmpeg error: {result.stderr}")
            return jsonify({
                "error": "FFmpeg failed",
                "details": result.stderr,
                "command": ' '.join(cmd)
            }), 500
        
        if not os.path.exists(output_path):
            logger.error("Video file was not created")
            return jsonify({
                "error": "Video file was not created",
                "ffmpeg_output": result.stdout,
                "ffmpeg_error": result.stderr
            }), 500
        
        # Get file size
        file_size = os.path.getsize(output_path)
        
        logger.info(f"✅ Video created successfully: {output_path} ({file_size} bytes)")
        
        return jsonify({
            "message": "Video created successfully",
            "video_path": output_path,
            "video_url": f"/download/{os.path.basename(output_path)}",
            "filename": os.path.basename(output_path),
            "size": file_size
        }), 200
        
    except requests.exceptions.Timeout:
        logger.error("Download timeout")
        return jsonify({"error": "Download timeout"}), 504
    except subprocess.TimeoutExpired:
        logger.error("FFmpeg timeout")
        return jsonify({"error": "FFmpeg timeout (processing took > 5 minutes)"}), 504
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route('/download/<filename>')
def download_file(filename):
    """Download generated video file"""
    try:
        logger.info(f"Download requested: {filename}")
        filepath = os.path.join(TEMP_DIR, filename)
        if os.path.exists(filepath):
            return send_file(filepath, as_attachment=True, download_name=filename, mimetype='video/mp4')
        else:
            logger.error(f"File not found: {filepath}")
            return jsonify({"error": "File not found"}), 404
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Startup check
logger.info("=" * 50)
logger.info("FFmpeg Video API Starting...")
logger.info(f"Python version: {sys.version}")
logger.info(f"Working directory: {os.getcwd()}")
logger.info(f"Temp directory: {TEMP_DIR}")
logger.info(f"FFmpeg path: {FFMPEG_PATH}")
logger.info(f"FFmpeg exists: {os.path.exists(FFMPEG_PATH)}")
logger.info("=" * 50)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"Starting Flask app on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
