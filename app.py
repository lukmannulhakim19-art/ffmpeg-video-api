from flask import Flask, request, jsonify, send_file
import subprocess
import os
import uuid
import requests
from werkzeug.utils import secure_filename

app = Flask(__name__)

TEMP_DIR = '/tmp'
os.makedirs(TEMP_DIR, exist_ok=True)

@app.route('/')
def home():
    return jsonify({
        "service": "FFmpeg Video Creation API",
        "endpoints": {
            "/create-video": "POST - Create video from image + audio (supports both URL and file upload)",
            "/health": "GET - Health check"
        }
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

@app.route('/create-video', methods=['POST'])
def create_video():
    try:
        # Cek apakah request JSON (URL) atau multipart (file upload)
        if request.is_json:
            # Handle JSON request dengan URL
            data = request.get_json()
            audio_url = data.get('audio_url')
            image_url = data.get('image_url')
            output_filename = data.get('output_filename', 'output_video.mp4')
            
            if not audio_url or not image_url:
                return jsonify({"error": "audio_url and image_url are required"}), 400
            
            unique_id = str(uuid.uuid4())[:8]
            audio_path = os.path.join(TEMP_DIR, f'audio_{unique_id}.mp3')
            image_path = os.path.join(TEMP_DIR, f'image_{unique_id}.jpg')
            
            # Download files
            print(f"Downloading audio from {audio_url}")
            audio_response = requests.get(audio_url, timeout=60)
            with open(audio_path, 'wb') as f:
                f.write(audio_response.content)
            
            print(f"Downloading image from {image_url}")
            image_response = requests.get(image_url, timeout=60)
            with open(image_path, 'wb') as f:
                f.write(image_response.content)
        
        else:
            # Handle multipart form-data (file upload)
            if 'audio' not in request.files or 'image' not in request.files:
                return jsonify({"error": "audio and image files are required"}), 400
            
            audio_file = request.files['audio']
            image_file = request.files['image']
            output_filename = request.form.get('output_filename', 'output_video.mp4')
            
            unique_id = str(uuid.uuid4())[:8]
            audio_path = os.path.join(TEMP_DIR, f'audio_{unique_id}_{secure_filename(audio_file.filename)}')
            image_path = os.path.join(TEMP_DIR, f'image_{unique_id}_{secure_filename(image_file.filename)}')
            
            audio_file.save(audio_path)
            image_file.save(image_path)
        
        # Create video dengan FFmpeg
        output_path = os.path.join(TEMP_DIR, f'video_{unique_id}_{output_filename}')
        
        print(f"Creating video: {output_path}")
        cmd = [
            'ffmpeg',
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
        
        # Cleanup input files
        if os.path.exists(audio_path):
            os.remove(audio_path)
        if os.path.exists(image_path):
            os.remove(image_path)
        
        if result.returncode != 0:
            return jsonify({
                "error": "FFmpeg failed",
                "details": result.stderr
            }), 500
        
        if not os.path.exists(output_path):
            return jsonify({"error": "Video file was not created"}), 500
        
        return jsonify({
            "message": "Video created successfully",
            "video_path": output_path,
            "video_url": f"/download/{os.path.basename(output_path)}",
            "filename": os.path.basename(output_path)
        }), 200
        
    except requests.exceptions.Timeout:
        return jsonify({"error": "Download timeout"}), 504
    except subprocess.TimeoutExpired:
        return jsonify({"error": "FFmpeg timeout"}), 504
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/download/<filename>')
def download_file(filename):
    try:
        filepath = os.path.join(TEMP_DIR, filename)
        if os.path.exists(filepath):
            return send_file(filepath, as_attachment=True, download_name=filename, mimetype='video/mp4')
        else:
            return jsonify({"error": "File not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
