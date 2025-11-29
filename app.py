from flask import Flask, request, send_file, jsonify
import subprocess
import os
import uuid
from werkzeug.utils import secure_filename
import tempfile

app = Flask(__name__)

@app.route('/create-video', methods=['POST'])
def create_video():
    """
    Endpoint untuk membuat video dari image + audio
    
    Input:
    - image: file (JPEG/PNG)
    - audio: file (MP3/WAV)
    
    Output:
    - video: file (MP4)
    """
    try:
        # Validasi input files
        if 'image' not in request.files:
            return jsonify({'error': 'Missing image file'}), 400
        
        if 'audio' not in request.files:
            return jsonify({'error': 'Missing audio file'}), 400
        
        image_file = request.files['image']
        audio_file = request.files['audio']
        
        # Validasi file tidak kosong
        if image_file.filename == '':
            return jsonify({'error': 'Image filename is empty'}), 400
        
        if audio_file.filename == '':
            return jsonify({'error': 'Audio filename is empty'}), 400
        
        # Generate unique ID untuk file
        video_id = str(uuid.uuid4())[:8]
        
        # Buat temporary directory
        temp_dir = tempfile.gettempdir()
        
        # Simpan file dengan nama unik
        image_ext = os.path.splitext(image_file.filename)[1] or '.jpg'
        audio_ext = os.path.splitext(audio_file.filename)[1] or '.mp3'
        
        image_path = os.path.join(temp_dir, f"image_{video_id}{image_ext}")
        audio_path = os.path.join(temp_dir, f"audio_{video_id}{audio_ext}")
        output_path = os.path.join(temp_dir, f"video_{video_id}.mp4")
        
        # Save uploaded files
        image_file.save(image_path)
        audio_file.save(audio_path)
        
        print(f"[INFO] Processing video {video_id}")
        print(f"[INFO] Image: {image_path} ({os.path.getsize(image_path)} bytes)")
        print(f"[INFO] Audio: {audio_path} ({os.path.getsize(audio_path)} bytes)")
        
        # FFmpeg command untuk create video
        ffmpeg_cmd = [
            'ffmpeg',
            '-loop', '1',                    # Loop image
            '-i', image_path,                # Input image
            '-i', audio_path,                # Input audio
            '-c:v', 'libx264',              # Video codec
            '-tune', 'stillimage',          # Optimize untuk still image
            '-c:a', 'aac',                  # Audio codec
            '-b:a', '192k',                 # Audio bitrate
            '-pix_fmt', 'yuv420p',          # Pixel format (kompatibilitas)
            '-shortest',                     # Duration = audio duration
            '-movflags', '+faststart',      # Optimize untuk web streaming
            '-y',                           # Overwrite output
            output_path
        ]
        
        # Execute FFmpeg
        print(f"[INFO] Running FFmpeg...")
        result = subprocess.run(
            ffmpeg_cmd, 
            capture_output=True, 
            text=True,
            timeout=300  # 5 minutes timeout
        )
        
        # Check jika FFmpeg gagal
        if result.returncode != 0:
            print(f"[ERROR] FFmpeg failed: {result.stderr}")
            return jsonify({
                'error': 'FFmpeg processing failed',
                'details': result.stderr
            }), 500
        
        # Check jika output file berhasil dibuat
        if not os.path.exists(output_path):
            return jsonify({'error': 'Output video file not created'}), 500
        
        output_size = os.path.getsize(output_path)
        print(f"[SUCCESS] Video created: {output_path} ({output_size} bytes)")
        
        # Cleanup input files (hemat disk space)
        try:
            os.remove(image_path)
            os.remove(audio_path)
        except Exception as e:
            print(f"[WARNING] Cleanup failed: {e}")
        
        # Kirim video file sebagai response
        return send_file(
            output_path, 
            mimetype='video/mp4',
            as_attachment=True,
            download_name=f'video_{video_id}.mp4',
            max_age=0  # No cache
        )
        
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'FFmpeg processing timeout (>5 minutes)'}), 500
    
    except Exception as e:
        print(f"[ERROR] {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500
    
    finally:
        # Cleanup output file setelah dikirim (optional)
        # Railway akan auto-cleanup /tmp saat restart
        pass

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'service': 'ffmpeg-video-api',
        'version': '1.0.0'
    })

@app.route('/', methods=['GET'])
def index():
    """Welcome page"""
    return jsonify({
        'service': 'FFmpeg Video Creation API',
        'endpoints': {
            '/create-video': 'POST - Create video from image + audio',
            '/health': 'GET - Health check'
        },
        'usage': {
            'method': 'POST',
            'url': '/create-video',
            'content_type': 'multipart/form-data',
            'parameters': {
                'image': 'file (JPEG/PNG)',
                'audio': 'file (MP3/WAV/M4A)'
            }
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
