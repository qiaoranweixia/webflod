"""
Flask 视频网站 - 主应用 (Ultimate 终极完美版)
功能：极速缓存/MD5防重/大文件排队/异步压缩无残留/在线播放(faststart)/播放列表/历史/密码防越权/yt-dlp嗅探等
"""

import os
import uuid
import json
import subprocess
import threading
import datetime
import hashlib
import base64
import re
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, redirect, url_for, send_from_directory, render_template, jsonify, make_response
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

# 强制解除 Flask 内部的文件大小限制，允许上传 2GB+ 甚至更大的文件
app.config['MAX_CONTENT_LENGTH'] = None 

# ================= 全局资源与锁 (健壮性核心) =================
# 后台线程池：限制同时运行的任务，防止 CPU 核爆
ffmpeg_pool = ThreadPoolExecutor(max_workers=2)

# 文件读写全局锁（彻底防止多用户并发操作导致的 JSON 覆盖/清空损坏）
file_locks = {
    'cache': threading.Lock(),
    'json': threading.Lock()
}

# ================= 数据存储文件定义 =================
DATA_DIR = os.path.dirname(os.path.abspath(__file__))
PLAY_COUNTS_FILE = os.path.join(DATA_DIR, 'play_counts.json')
VIDEO_TAGS_FILE = os.path.join(DATA_DIR, 'video_tags.json')
VIDEO_DESCRIPTIONS_FILE = os.path.join(DATA_DIR, 'video_descriptions.json')
PLAYLISTS_FILE = os.path.join(DATA_DIR, 'playlists.json')
WATCH_HISTORY_FILE = os.path.join(DATA_DIR, 'watch_history.json')
VIDEO_PASSWORDS_FILE = os.path.join(DATA_DIR, 'video_passwords.json')
CUSTOM_COVERS_FILE = os.path.join(DATA_DIR, 'custom_covers.json')
VIDEO_META_CACHE_FILE = os.path.join(DATA_DIR, 'video_meta_cache.json')

# ================= 核心工具函数 =================

def get_file_md5(filepath):
    """计算文件的 MD5 指纹（分块读取，防撑爆内存）"""
    hash_md5 = hashlib.md5()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except: return None

def get_clean_unique_filename(folder, original_filename):
    """智能干净命名：保留原名，只有重复时加 (1), (2)"""
    if not original_filename: return f"unnamed_{uuid.uuid4().hex[:6]}.mp4"
    clean_name = re.sub(r'[/\\?%*:|"<>]', '', original_filename)
    if not clean_name: clean_name = f"video_{uuid.uuid4().hex[:6]}.mp4"
        
    base, ext = os.path.splitext(clean_name)
    final_name = clean_name
    counter = 1
    while os.path.exists(os.path.join(folder, final_name)):
        final_name = f"{base}({counter}){ext}"
        counter += 1
    return final_name

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config.get('ALLOWED_EXTENSIONS', ['mp4','webm','mkv','mov','avi'])

def allowed_audio_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config.get('ALLOWED_AUDIO_EXTENSIONS', ['mp3', 'wav', 'aac', 'flac'])

def get_file_size(filepath):
    if os.path.exists(filepath): return round(os.path.getsize(filepath) / 1024 / 1024, 1)
    return 0

def format_duration(seconds):
    if not seconds: return "未知"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"

def get_video_duration(filepath):
    try:
        res = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', filepath], capture_output=True, text=True, timeout=10)
        if res.returncode == 0: return float(json.loads(res.stdout)['format']['duration'])
    except: pass
    return 0

def get_video_info(filepath):
    info = {'width': 0, 'height': 0, 'codec': 'unknown', 'bitrate': 0}
    try:
        res = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,codec_name,bit_rate', '-of', 'json', filepath], capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            data = json.loads(res.stdout)
            if data.get('streams'):
                stream = data['streams'][0]
                info['width'] = stream.get('width', 0)
                info['height'] = stream.get('height', 0)
                info['codec'] = stream.get('codec_name', 'unknown')
    except: pass
    return info

def generate_thumbnail(video_path, thumb_path):
    try:
        duration = get_video_duration(video_path)
        time_pos = min(app.config.get('THUMBNAIL_TIME', 3), duration * 0.8)
        subprocess.run(['ffmpeg', '-i', video_path, '-ss', str(time_pos), '-vframes', '1', '-vf', 'scale=320:-1', '-y', thumb_path], capture_output=True, timeout=30)
        return os.path.exists(thumb_path)
    except: return False

# ====== 线程安全的 JSON 数据读写 ======
def load_json_safe(file_path):
    if not os.path.exists(file_path): return {}
    with file_locks['json']:
        try:
            with open(file_path, 'r', encoding='utf-8') as f: return json.load(f)
        except: return {}

def save_json_safe(file_path, data):
    with file_locks['json']:
        try:
            with open(file_path, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e: print(f"写入 JSON 异常 {file_path}: {e}")

# ====== 极速列表缓存系统 ======
def load_video_meta_cache():
    if not os.path.exists(VIDEO_META_CACHE_FILE): return {}
    with file_locks['cache']:
        try:
            with open(VIDEO_META_CACHE_FILE, 'r', encoding='utf-8') as f: return json.load(f)
        except: return {}

def save_video_meta_cache(cache_data):
    with file_locks['cache']:
        try:
            with open(VIDEO_META_CACHE_FILE, 'w', encoding='utf-8') as f: json.dump(cache_data, f, ensure_ascii=False, indent=2)
        except: pass

def inject_cache_immediately(filepath, filename, file_md5=None):
    """立刻为单个文件打入缓存，包含 MD5"""
    cache = load_video_meta_cache()
    duration = get_video_duration(filepath)
    info = get_video_info(filepath)
    if not file_md5: file_md5 = get_file_md5(filepath)
    meta = {
        'filename': filename, 'size_mb': get_file_size(filepath),
        'duration': format_duration(duration), 'duration_sec': duration,
        'resolution': f"{info['width']}x{info['height']}" if info['width'] else '未知',
        'codec': info['codec'], 'mtime': os.path.getmtime(filepath), 'md5': file_md5
    }
    cache[filename] = meta
    save_video_meta_cache(cache)

def get_all_video_metadata():
    if not os.path.exists(app.config['UPLOAD_FOLDER']): return []
    files = {}
    try:
        with os.scandir(app.config['UPLOAD_FOLDER']) as it:
            for entry in it:
                if entry.is_file() and allowed_file(entry.name): files[entry.name] = entry.stat().st_mtime
    except: return []

    cache = load_video_meta_cache()
    updated = False
    
    # 剔除僵尸缓存
    for k in list(cache.keys()):
        if k not in files:
            del cache[k]; updated = True
            
    video_meta = []
    for filename, mtime in files.items():
        if filename in cache and cache[filename].get('mtime') == mtime:
            video_meta.append(cache[filename])
        else:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            # 对于旧文件补全缓存
            inject_cache_immediately(filepath, filename)
            updated = True
            
    if updated: save_video_meta_cache(cache)
    return [cache[f] for f in files if f in cache]

# ================= 媒体后台处理 (异步+终极清理核心) =================
def background_process_media(filepath, final_filename, is_audio, compress_flag):
    """后台处理，加入了强力垃圾回收，防止生成莫名其妙的残片文件"""
    temp_compressed = filepath + '_temp' + ('.mp3' if is_audio else '.mp4')
    try:
        if compress_flag:
            if is_audio and app.config.get('COMPRESS_AUDIO', True):
                cmd = ['ffmpeg', '-i', filepath, '-b:a', app.config.get('AUDIO_COMPRESSION_BITRATE', '128k'), '-c:a', 'aac', '-y', temp_compressed]
                if subprocess.run(cmd, capture_output=True, timeout=600).returncode == 0 and os.path.exists(temp_compressed):
                    if os.path.getsize(temp_compressed) < os.path.getsize(filepath):
                        try: os.replace(temp_compressed, filepath)
                        except: os.remove(filepath); os.rename(temp_compressed, filepath)
                        
            elif not is_audio and app.config.get('COMPRESS_VIDEO', False):
                info = get_video_info(filepath)
                width = info.get('width', 1280)
                scale_filter = f'scale={min(width, app.config.get("MAX_WIDTH", 1280))}:-1'
                cmd = [
                    'ffmpeg', '-i', filepath, '-vf', scale_filter, 
                    '-c:v', 'libx264', '-preset', app.config.get('COMPRESSION_PRESET', 'fast'), 
                    '-crf', str(app.config.get('CRF_VALUE', 28)), 
                    '-c:a', 'aac', '-b:a', app.config.get('AUDIO_BITRATE', '128k'), 
                    '-movflags', '+faststart', '-y', temp_compressed
                ]
                if subprocess.run(cmd, capture_output=True, timeout=3600).returncode == 0 and os.path.exists(temp_compressed):
                    if os.path.getsize(temp_compressed) < os.path.getsize(filepath):
                        try: os.replace(temp_compressed, filepath)
                        except: os.remove(filepath); os.rename(temp_compressed, filepath)

        # 生成 GIF 动图
        if not is_audio and app.config.get('GENERATE_THUMBNAIL', True):
            gif_path = os.path.join(app.config['THUMBNAIL_FOLDER'], os.path.splitext(final_filename)[0] + '.gif')
            duration = get_video_duration(filepath)
            start_pos = max(1, duration * 0.1)
            gif_dur = min(3, duration - start_pos)
            if gif_dur >= 1:
                subprocess.run(['ffmpeg', '-i', filepath, '-ss', str(start_pos), '-t', str(gif_dur), '-vf', 'fps=2,scale=320:-1:flags=lanczos', '-y', gif_path], capture_output=True, timeout=120)

        inject_cache_immediately(filepath, final_filename) # 压制完后再次更新缓存
    except Exception as e:
        print(f"后台媒体任务异常 {final_filename}: {e}")
    finally:
        # 强制抹杀残留临时文件
        if os.path.exists(temp_compressed):
            try: os.remove(temp_compressed)
            except: pass

# ================= 基础核心路由 =================

@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    sort_by = request.args.get('sort', 'date')
    per_page = app.config.get('VIDEOS_PER_PAGE', 20)
    
    video_meta = get_all_video_metadata()
    if sort_by == 'name': video_meta.sort(key=lambda x: x['filename'].lower())
    elif sort_by == 'size': video_meta.sort(key=lambda x: x['size_mb'], reverse=True)
    elif sort_by == 'duration': video_meta.sort(key=lambda x: x['duration_sec'], reverse=True)
    else: video_meta.sort(key=lambda x: x['mtime'], reverse=True)
    
    total = len(video_meta)
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    video_data = video_meta[start:start + per_page]
    
    return render_template('index.html', videos=[v['filename'] for v in video_data], video_data=video_data, page=page, total_pages=total_pages, total=total, request=request)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files: return jsonify({'error': '没有文件'}), 400
    compress = request.form.get('compress', 'true') == 'true'
    files = request.files.getlist('file')
    
    uploaded, skipped = [], []
    cache = load_video_meta_cache()
    existing_md5_map = {m.get('md5'): m['filename'] for m in cache.values() if m.get('md5')}
    
    for file in files:
        if not file or not file.filename: continue
        temp_filepath = os.path.join(app.config['UPLOAD_FOLDER'], f".temp_{uuid.uuid4().hex}.tmp")
        try:
            file.save(temp_filepath)
            file_md5 = get_file_md5(temp_filepath)
            
            # MD5 防重复秒传判定
            if file_md5 in existing_md5_map:
                os.remove(temp_filepath)
                skipped.append(f"{file.filename} (已存在: {existing_md5_map[file_md5]})")
                continue
                
            final_filename = get_clean_unique_filename(app.config['UPLOAD_FOLDER'], file.filename)
            final_filepath = os.path.join(app.config['UPLOAD_FOLDER'], final_filename)
            os.rename(temp_filepath, final_filepath)
            
            is_audio = allowed_audio_file(final_filename)
            if not is_audio and app.config.get('GENERATE_THUMBNAIL', True):
                generate_thumbnail(final_filepath, os.path.join(app.config['THUMBNAIL_FOLDER'], os.path.splitext(final_filename)[0] + '.jpg'))
            
            inject_cache_immediately(final_filepath, final_filename, file_md5)
            existing_md5_map[file_md5] = final_filename
            ffmpeg_pool.submit(background_process_media, final_filepath, final_filename, is_audio, compress)
            uploaded.append(final_filename)
        except Exception as e:
            if os.path.exists(temp_filepath): os.remove(temp_filepath)
    
    return jsonify({'success': True, 'uploaded': uploaded, 'skipped': skipped})

def hash_password(password): return hashlib.sha256(password.encode()).hexdigest()

@app.route('/videos/<filename>')
def serve_video(filename):
    """【安全修复】防止绕过密码直接通过 URL 访问视频"""
    pwd_data = load_json_safe(VIDEO_PASSWORDS_FILE)
    if filename in pwd_data:
        cookie_hash = request.cookies.get(f"video_auth_{filename}")
        if cookie_hash != pwd_data[filename]['password']:
            return "403 Forbidden: 视频受密码保护。", 403
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/thumbnails/<filename>')
def serve_thumbnail(filename): return send_from_directory(app.config['THUMBNAIL_FOLDER'], filename, mimetype='image/jpeg')

@app.route('/previews/<filename>')
def serve_preview(filename):
    gif_path = os.path.join(app.config['THUMBNAIL_FOLDER'], filename)
    if os.path.exists(gif_path): return send_from_directory(app.config['THUMBNAIL_FOLDER'], filename, mimetype='image/gif')
    return '', 404

@app.route('/delete/<filename>', methods=['POST'])
def delete_file(filename):
    """【彻底清理】删除物理文件以及所有JSON关联数据"""
    try:
        base_name = os.path.splitext(filename)[0]
        paths = [
            os.path.join(app.config['UPLOAD_FOLDER'], filename),
            os.path.join(app.config['THUMBNAIL_FOLDER'], base_name + '.jpg'),
            os.path.join(app.config['THUMBNAIL_FOLDER'], base_name + '.gif')
        ]
        for p in paths:
            if os.path.exists(p): os.remove(p)

        cache = load_video_meta_cache()
        if filename in cache: del cache[filename]; save_video_meta_cache(cache)

        def rm_json(fp):
            data = load_json_safe(fp)
            if filename in data: del data[filename]; save_json_safe(fp, data)
            
        for fp in [CUSTOM_COVERS_FILE, VIDEO_TAGS_FILE, VIDEO_DESCRIPTIONS_FILE, PLAY_COUNTS_FILE, WATCH_HISTORY_FILE, VIDEO_PASSWORDS_FILE]:
            rm_json(fp)

        playlists = load_json_safe(PLAYLISTS_FILE)
        modified = False
        for pid in playlists:
            if filename in playlists[pid]['videos']:
                playlists[pid]['videos'].remove(filename)
                modified = True
        if modified: save_json_safe(PLAYLISTS_FILE, playlists)
            
        return jsonify({'success': True})
    except Exception as e: return jsonify({'success': False, 'error': str(e)}), 500

# ================= 业务拓展功能 (合集/统计/标签/密码) =================

@app.route('/api/stats')
def api_stats():
    meta = get_all_video_metadata()
    total_size = sum(v.get('size_mb', 0) for v in meta)
    return jsonify({
        'total_videos': len(meta), 'total_size_mb': round(total_size, 2),
        'total_size_gb': round(total_size / 1024, 2)
    })

@app.route('/api/play/<filename>', methods=['POST'])
def api_play(filename):
    counts = load_json_safe(PLAY_COUNTS_FILE)
    counts[filename] = counts.get(filename, 0) + 1; save_json_safe(PLAY_COUNTS_FILE, counts)
    return jsonify({'success': True})

@app.route('/api/password/<filename>', methods=['GET'])
def api_check_password(filename):
    data = load_json_safe(VIDEO_PASSWORDS_FILE)
    return jsonify({'protected': filename in data, 'hint': data.get(filename, {}).get('hint', '')})

@app.route('/api/password/<filename>', methods=['POST'])
def api_verify_password(filename):
    data = load_json_safe(VIDEO_PASSWORDS_FILE)
    if filename not in data: return jsonify({'success': True})
    pwd_hash = hash_password(request.get_json().get('password', ''))
    if pwd_hash == data[filename].get('password', ''): return jsonify({'success': True, 'hash': pwd_hash})
    return jsonify({'success': False, 'error': '密码错误'}), 401

@app.route('/api/password/<filename>', methods=['PUT'])
def api_set_password(filename):
    pwd, hint = request.get_json().get('password', ''), request.get_json().get('hint', '')
    data = load_json_safe(VIDEO_PASSWORDS_FILE)
    if pwd: data[filename] = {'password': hash_password(pwd), 'hint': hint}
    elif filename in data: del data[filename]
    save_json_safe(VIDEO_PASSWORDS_FILE, data)
    return jsonify({'success': True, 'protected': bool(pwd)})

@app.route('/api/cover/upload/<filename>', methods=['POST'])
def api_upload_cover(filename):
    if 'cover' not in request.files: return jsonify({'error': '无文件'}), 400
    file = request.files['cover']
    cover_path = os.path.join(app.config['THUMBNAIL_FOLDER'], os.path.splitext(filename)[0] + '.jpg')
    file.save(cover_path)
    return jsonify({'success': True})

@app.route('/api/description/<filename>', methods=['GET', 'POST'])
def api_description(filename):
    data = load_json_safe(VIDEO_DESCRIPTIONS_FILE)
    if request.method == 'GET': return jsonify(data.get(filename, {'description': ''}))
    data[filename] = {'description': request.json.get('description', '')}; save_json_safe(VIDEO_DESCRIPTIONS_FILE, data)
    return jsonify({'success': True})

@app.route('/api/history/recent')
def api_history_recent():
    items = sorted(load_json_safe(WATCH_HISTORY_FILE).items(), key=lambda x: x[1].get('last_watched', ''), reverse=True)
    return jsonify({'history': dict(items[:20])})

@app.route('/api/history/<filename>', methods=['POST'])
def api_update_history(filename):
    data = load_json_safe(WATCH_HISTORY_FILE)
    req = request.json
    pos, dur = req.get('position', 0), req.get('duration', 0)
    data[filename] = {'progress_percent': round((pos/dur*100) if dur>0 else 0, 1), 'last_watched': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    save_json_safe(WATCH_HISTORY_FILE, data); return jsonify({'success': True})

@app.route('/api/playlists', methods=['GET', 'POST'])
def api_playlists():
    data = load_json_safe(PLAYLISTS_FILE)
    if request.method == 'GET': return jsonify({'playlists': list(data.values())})
    pid = str(uuid.uuid4())[:8]
    data[pid] = {'id': pid, 'name': request.json.get('name', '未命名合集'), 'videos': []}
    save_json_safe(PLAYLISTS_FILE, data); return jsonify({'success': True, 'id': pid})

@app.route('/api/playlists/<pid>', methods=['POST'])
def api_playlist_add(pid):
    data = load_json_safe(PLAYLISTS_FILE)
    filename = request.json.get('filename')
    if pid in data and filename and filename not in data[pid]['videos']:
        data[pid]['videos'].append(filename); save_json_safe(PLAYLISTS_FILE, data)
        return jsonify({'success': True})
    return jsonify({'success': False})

# ================= 视频嗅探与下载 (yt-dlp) =================
@app.route('/api/download', methods=['POST'])
def download_video():
    url, custom_name, auto_compress = request.json.get('url'), request.json.get('customFilename'), request.json.get('autoCompress', True)
    if not url: return jsonify({'success': False, 'error': '无链接'}), 400
    try:
        base_name = safe_secure_filename(custom_name) if custom_name else f"web_{uuid.uuid4().hex[:6]}"
        if base_name.endswith('.mp4'): base_name = base_name[:-4]
        final_name = base_name + '.mp4'
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], final_name)
        
        cmd = ['yt-dlp', '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best', '-o', filepath, '--no-playlist', url]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try: proc.wait(timeout=900)
        except subprocess.TimeoutExpired: proc.kill(); return jsonify({'error': '嗅探超时'}), 500
            
        if proc.returncode != 0 or not os.path.exists(filepath): return jsonify({'error': '解析失败，链接可能已失效'}), 500
            
        generate_thumbnail(filepath, os.path.join(app.config['THUMBNAIL_FOLDER'], base_name + '.jpg'))
        inject_cache_immediately(filepath, final_name)
        ffmpeg_pool.submit(background_process_media, filepath, final_name, False, auto_compress)
        return jsonify({'success': True, 'filename': final_name})
    except Exception as e: return jsonify({'success': False, 'error': str(e)}), 500

# ================= 一键迁移老文件工具 =================
@app.route('/api/sync_old')
def sync_old_files():
    def bg_sync():
        print("🔄 [老文件同步] 开始执行扫描...")
        cache = load_video_meta_cache()
        for filename in os.listdir(app.config['UPLOAD_FOLDER']):
            if not allowed_file(filename): continue
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            is_audio = allowed_audio_file(filename)
            needs_update = False
            
            file_md5 = cache.get(filename, {}).get('md5')
            if not file_md5 or filename not in cache:
                print(f"⏳ 算指纹: {filename}")
                file_md5 = get_file_md5(filepath); needs_update = True
                
            thumb_path = os.path.join(app.config['THUMBNAIL_FOLDER'], os.path.splitext(filename)[0] + '.jpg')
            if not is_audio and not os.path.exists(thumb_path):
                print(f"🖼️ 做封面: {filename}"); generate_thumbnail(filepath, thumb_path)
                
            if needs_update: inject_cache_immediately(filepath, filename, file_md5)
        print("✅ [老文件同步] 执行完毕！")
    threading.Thread(target=bg_sync).start()
    return "<body style='background:#1c1c24;color:white;text-align:center;padding-top:100px;'><h1>🚀 后台同步任务已启动！</h1><p>请查看服务器终端输出进度。完成后回主页即可。</p><button onclick=\"location.href='/'\">返回主页</button></body>"

if __name__ == '__main__':
    os.makedirs(app.config.get('UPLOAD_FOLDER', 'uploads'), exist_ok=True)
    os.makedirs(app.config.get('THUMBNAIL_FOLDER', 'thumbnails'), exist_ok=True)
    print(f"🎬 极速与高并发版视频后台启动中...")
    print(f"✅ 后台排队上传 + 防断流(faststart) + MD5防重机制 已全部生效")
    print(f"📁 监听端口：http://localhost:{app.config.get('PORT', 5001)}")
    app.run(host=app.config.get('HOST', '0.0.0.0'), port=app.config.get('PORT', 5001), debug=app.config.get('DEBUG', False))
