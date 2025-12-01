from flask import Flask, request, jsonify, send_file
import subprocess
import os
import uuid
import requests
import base64
import shutil
from werkzeug.utils import secure_filename

app = Flask(__name__)

TEMP_DIR = '/tmp'
os.makedirs(TEMP_DIR, exist_ok=True)

# Find FFmpeg executable
FFMPEG_PATH = shutil.which('ffmpeg') or '/usr/bin/ffmpeg'
print(f"FFmpeg path: {FFMPEG_PATH}")

@app.route('/')
def home():
    return jsonify({
        "service": "FFmpeg Video Creation API",
        "endpoints": {
            "/create-video": "POST - Create video (supports URL, file upload, or base64)",
            "/health": "GET - Health check",
            "/test-ffmpeg": "GET - Test FFmpeg installation"
        }
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

@app.route('/test-ffmpeg')
def test_ffmpeg():
    """Test FFmpeg installation"""
    if not os.path.exists(FFMPEG_PATH):
        return jsonify({
            "status": "error",
            "message": f"FFmpeg not found at {FFMPEG_PATH}",
            "checked_paths": ['/usr/bin/ffmpeg', '/usr/local/bin/ffmpeg', '/bin/ffmpeg']
        }), 404
    
    try:
        result = subprocess.run([FFMPEG_PATH, '-version'], capture_output=True, text=True, timeout=5)
        return jsonify({
            "status": "success",
            "ffmpeg_path": FFMPEG_PATH,
            "version": result.stdout.split('\n')[0] if result.stdout else "Unknown"
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/create-video', methods=['POST'])
def create_video():
    try:
        unique_id = str(uuid.uuid4())[:8]
        audio_path = None
        image_path = None
        
        # Check if request is JSON (base64 or URL)
        if request.is_json:
            data = request.get_json()
            
            # Handle base64 input
            if 'image' in data and 'audio' in data:
                print("Processing base64 data...")
                
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
                except Exception as e:
                    return jsonify({"error": f"Base64 decode error: {str(e)}"}), 400
                
                # Save to files
                image_path = os.path.join(TEMP_DIR, f'image_{unique_id}.jpg')
                audio_path = os.path.join(TEMP_DIR, f'audio_{unique_id}.mp3')
                
                with open(image_path, 'wb') as f:
                    f.write(image_data)
                
                with open(audio_path, 'wb') as f:
                    f.write(audio_data)
                
                output_filename = data.get('output_filename', 'output_video.mp4')
            
            # Handle URL input
            elif 'audio_url' in data and 'image_url' in data:
                print("Processing URL data...")
                audio_url = data['audio_url']
                image_url = data['image_url']
                output_filename = data.get('output_filename', 'output_video.mp4')
                
                audio_path = os.path.join(TEMP_DIR, f'audio_{unique_id}.mp3')
                image_path = os.path.join(TEMP_DIR, f'image_{unique_id}.jpg')
                
                # Download files
                print(f"Downloading audio from {audio_url}")
                try:
                    audio_response = requests.get(audio_url, timeout=60)
                    audio_response.raise_for_status()
                    with open(audio_path, 'wb') as f:
                        f.write(audio_response.content)
                except Exception as e:
                    return jsonify({"error": f"Failed to download audio: {str(e)}"}), 400
                
                print(f"Downloading image from {image_url}")
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
                return jsonify({"error": "Invalid JSON input. Provide either base64 (image/audio) or URLs (audio_url/image_url)"}), 400
        
        # Handle multipart file upload
        elif 'audio' in request.files and 'image' in request.files:
            print("Processing file upload...")
            audio_file = request.files['audio']
            image_file = request.files['image']
            output_filename = request.form.get('output_filename', 'output_video.mp4')
            
            audio_path = os.path.join(TEMP_DIR, f'audio_{unique_id}_{secure_filename(audio_file.filename)}')
            image_path = os.path.join(TEMP_DIR, f'image_{unique_id}_{secure_filename(image_file.filename)}')
            
            audio_file.save(audio_path)
            image_file.save(image_path)
        
        else:
            return jsonify({"error": "Invalid input. Provide either JSON (base64/URLs) or multipart files"}), 400
        
        # Validate files exist
        if not os.path.exists(audio_path) or not os.path.exists(image_path):
            return jsonify({"error": "Failed to save input files"}), 500
        
        # Create video with FFmpeg
        output_path = os.path.join(TEMP_DIR, f'video_{unique_id}_{output_filename}')
        
        print(f"Creating video: {output_path}")
        print(f"Using FFmpeg: {FFMPEG_PATH}")
        
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
        
        print(f"FFmpeg command: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        # Cleanup input files
        if os.path.exists(audio_path):
            os.remove(audio_path)
        if os.path.exists(image_path):
            os.remove(image_path)
        
        if result.returncode != 0:
            print(f"FFmpeg error: {result.stderr}")
            return jsonify({
                "error": "FFmpeg failed",
                "details": result.stderr,
                "command": ' '.join(cmd)
            }), 500
        
        if not os.path.exists(output_path):
            return jsonify({
                "error": "Video file was not created",
                "ffmpeg_output": result.stdout,
                "ffmpeg_error": result.stderr
            }), 500
        
        # Get file size
        file_size = os.path.getsize(output_path)
        
        print(f"Video created successfully: {output_path} ({file_size} bytes)")
        
        return jsonify({
            "message": "Video created successfully",
            "video_path": output_path,
            "video_url": f"/download/{os.path.basename(output_path)}",
            "filename": os.path.basename(output_path),
            "size": file_size
        }), 200
        
    except requests.exceptions.Timeout:
        return jsonify({"error": "Download timeout"}), 504
    except subprocess.TimeoutExpired:
        return jsonify({"error": "FFmpeg timeout (processing took > 5 minutes)"}), 504
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/download/<filename>')
def download_file(filename):
    """Download generated video file"""
    try:
        filepath = os.path.join(TEMP_DIR, filename)
        if os.path.exists(filepath):
            response = send_file(filepath, as_attachment=True, download_name=filename, mimetype='video/mp4')
            # Schedule file deletion after download
            # Note: In production, you'd want a cleanup job
            return response
        else:
            return jsonify({"error": "File not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
```

---

## File 2: `requirements.txt`
```
flask==3.0.0
gunicorn==21.2.0
requests==2.31.0
werkzeug==3.0.0
