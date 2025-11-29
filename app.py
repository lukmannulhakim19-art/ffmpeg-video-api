from flask import Flask, request, send_file, jsonify
import subprocess
import os
import uuid
import tempfile
import base64
import re

app = Flask(__name__)

def decode_base64_file(data_uri):
    """Decode base64 data URI to bytes"""
    # Extract base64 data from data URI
    # Format: data:mime/type;base64,BASE64_DATA
    match = re.match(r'data:([^;]+);base64,(.+)', data_uri)
    if match:
        mime_type = match.group(1)
        base64_data = match.group(2)
        file_data = base64.b64decode(base64_data)
        return file_data, mime_type
    return None, None

@app.route('/create-video', methods=['POST'])
def create_video():
    """
    Endpoint untuk membuat video dari image + audio
    Supports both file upload and base64 data URI
    """
    try:
        temp_dir = tempfile.gettempdir()
        video_id = str(uuid.uuid4())[:8]
        
        # Check if request is JSON (base64) or form-data (file upload)
        if request.is_json:
            data = request.get_json()
            
            if 'image' not in data or 'audio' not in data:
                return jsonify({'error': 'Missing image or audio in JSON'}), 400
            
            # Decode base64 image
            image_data, image_mime = decode_base64_file(data['image'])
            if not image_data:
                return jsonify({'error': 'Invalid image data URI'}), 400
            
            # Decode base64 audio
            audio_data, audio_mime = decode_base64_file(data['audio'])
            if not audio_data:
                return jsonify({'error': 'Invalid audio data URI'}), 400
            
            # Determine file extensions
            image_ext = '.jpg' if 'jpeg' in image_mime else '.png'
            audio_ext = '.mp3' if 'mpeg' in audio_mime else '.wav'
            
            # Save to temp files
            image_path = os.path.join(temp_dir, f"image_{video_id}{image_ext}")
            audio_path = os.path.join(temp_dir, f"audio_{video_id}{audio_ext}")
            
            with open(image_path, 'wb') as f:
                f.write(image_data)
            
            with open(audio_path, 'wb') as f:
                f.write(audio_data)
            
            print(f"[INFO] Decoded from base64")
        
        else:
            # File upload (original method)
            if 'image' not in request.files or 'audio' not in request.files:
                return jsonify({'error': 'Missing image or audio files'}), 400
            
            image_file = request.files['image']
            audio_file = request.files['audio']
            
            if image_file.filename == '' or audio_file.filename == '':
                return jsonify({'error': 'Empty filename'}), 400
            
            image_ext = os.path.splitext(image_file.filename)[1] or '.jpg'
            audio_ext = os.path.splitext(audio_file.filename)[1] or '.mp3'
            
            image_path = os.path.join(temp_dir, f"image_{video_id}{image_ext}")
            audio_path = os.path.join(temp_dir, f"audio_{video_id}{audio_ext}")
            
            image_file.save(image_path)
            audio_file.save(audio_path)
            
            print(f"[INFO] Files uploaded")
        
        output_path = os.path.join(temp_dir, f"video_{video_id}.mp4")
        
        print(f"[INFO] Processing video {video_id}")
        print(f"[INFO] Image: {image_path} ({os.path.getsize(image_path)} bytes)")
        print(f"[INFO] Audio: {audio_path} ({os.path.getsize(audio_path)} bytes)")
        
        # FFmpeg command
        ffmpeg_cmd = [
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
            '-movflags', '+faststart',
            '-y',
            output_path
        ]
        
        print(f"[INFO] Running FFmpeg...")
        result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode != 0:
            print(f"[ERROR] FFmpeg failed: {result.stderr}")
            return jsonify({
                'error': 'FFmpeg processing failed',
                'details': result.stderr
            }), 500
        
        if not os.path.exists(output_path):
            return jsonify({'error': 'Output video not created'}), 500
        
        output_size = os.path.getsize(output_path)
        print(f"[SUCCESS] Video created: {output_path} ({output_size} bytes)")
        
        # Cleanup
        try:
            os.remove(image_path)
            os.remove(audio_path)
        except Exception as e:
            print(f"[WARNING] Cleanup failed: {e}")
        
        return send_file(
            output_path,
            mimetype='video/mp4',
            as_attachment=True,
            download_name=f'video_{video_id}.mp4',
            max_age=0
        )
        
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'FFmpeg timeout'}), 500
    
    except Exception as e:
        print(f"[ERROR] {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'service': 'ffmpeg-video-api',
        'version': '1.0.0'
    })

@app.route('/', methods=['GET'])
def index():
    return jsonify({
        'service': 'FFmpeg Video Creation API',
        'endpoints': {
            '/create-video': 'POST - Create video from image + audio (supports both URL and file upload)',
            '/health': 'GET - Health check'
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
```

4. Scroll bawah, klik **"Commit changes"**
5. Railway akan auto-redeploy (tunggu 2-3 menit)

---

## 🎯 **WORKFLOW FINAL:**
```
... → Prepare for FFmpeg → Convert to Base64 → Create Video (HTTP) → Upload
