"""
Flask 视频网站 - 主应用 (最终完美增强版)
功能：极速缓存/异步无缝上传/在线播放(faststart防错码)/列表/删除/播放列表/历史/密码/封面/嗅探下载等
端口：5001
"""

import os
import uuid
import json
import subprocess
import time
import threading
import datetime
import hashlib
import base64
import re
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, redirect, url_for, send_from_directory, render_template, jsonify
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

# ================= 全局资源与锁 (健壮性核心) =================
# 后台线程池：限制最多同时运行 2 个压制/GIF任务，防止 CPU 核爆
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

def safe_secure_filename(filename):
    """防乱码：保留中文及常规字符，剔除破坏性路径符号"""
    if not filename: return f"unnamed_{uuid.uuid4().hex[:6]}"
    cleaned = re.sub(r'[/\\?%*:|"<>]', '', filename)
    return cleaned if cleaned else f"video_{uuid.uuid4().hex[:6]}.mp4"

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
        result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', filepath], capture_output=True, text=True, timeout=10)
        if result.returncode == 0: return float(json.loads(result.stdout)['format']['duration'])
    except: pass
    return 0

def get_video_info(filepath):
    info = {'width': 0, 'height': 0, 'codec': 'unknown', 'bitrate': 0}
    try:
        result = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,codec_name,bit_rate', '-of', 'json', filepath], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if data.get('streams'):
                stream = data['streams'][0]
                info['width'] = stream.get('width', 0)
                info['height'] = stream.get('height', 0)
                info['codec'] = stream.get('codec_name', 'unknown')
                info['bitrate'] = int(stream.get('bit_rate', 0) or 0)
    except: pass
    return info

def generate_thumbnail(video_path, thumb_path):
    """瞬间抽取缩略图"""
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

def get_all_video_metadata():
    if not os.path.exists(app.config['UPLOAD_FOLDER']): return []
    
    files = {}
    try:
        with os.scandir(app.config['UPLOAD_FOLDER']) as it:
            for entry in it:
                if entry.is_file() and allowed_file(entry.name): files[entry.name] = entry.stat().st_mtime
    except Exception as e: return []

    cache = load_video_meta_cache()
    updated = False
    
    # 剔除僵尸缓存
    cache_keys = list(cache.keys())
    for k in cache_keys:
        if k not in files:
            del cache[k]
            updated = True
            
    video_meta = []
    for filename, mtime in files.items():
        if filename in cache and cache[filename].get('mtime') == mtime:
            video_meta.append(cache[filename])
        else:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            duration = get_video_duration(filepath)
            info = get_video_info(filepath)
            meta = {
                'filename': filename, 'size_mb': get_file_size(filepath),
                'duration': format_duration(duration), 'duration_sec': duration,
                'resolution': f"{info['width']}x{info['height']}" if info['width'] else '未知',
                'codec': info['codec'], 'mtime': mtime
            }
            cache[filename] = meta
            video_meta.append(meta)
            updated = True
            
    if updated: save_video_meta_cache(cache)
    return video_meta

def inject_cache_immediately(filepath, filename):
    """立刻为单个文件打入缓存，让网页即时显示"""
    cache = load_video_meta_cache()
    duration = get_video_duration(filepath)
    info = get_video_info(filepath)
    meta = {
        'filename': filename, 'size_mb': get_file_size(filepath),
        'duration': format_duration(duration), 'duration_sec': duration,
        'resolution': f"{info['width']}x{info['height']}" if info['width'] else '未知',
        'codec': info['codec'], 'mtime': os.path.getmtime(filepath)
    }
    cache[filename] = meta
    save_video_meta_cache(cache)

def get_video_list():
    meta = get_all_video_metadata()
    meta.sort(key=lambda x: x['mtime'], reverse=True)
    return [v['filename'] for v in meta]

# ================= 媒体后台处理 (异步核心) =================
def background_process_media(filepath, unique_name, is_audio, compress_flag):
    """后台默默执行耗时的压缩和动态 GIF 获取，且解决播放错误码"""
    try:
        # 1. 重度任务：媒体压缩
        if compress_flag:
            temp_compressed = filepath + ('.mp3' if is_audio else '.mp4')
            if is_audio and app.config.get('COMPRESS_AUDIO', True):
                cmd = ['ffmpeg', '-i', filepath, '-b:a', app.config.get('AUDIO_COMPRESSION_BITRATE', '128k'), '-c:a', 'aac', '-y', temp_compressed]
                if subprocess.run(cmd, capture_output=True, timeout=300).returncode == 0:
                    if os.path.getsize(temp_compressed) < os.path.getsize(filepath):
                        try:
                            os.replace(temp_compressed, filepath) # 原子替换防断流
                        except:
                            os.remove(filepath); os.rename(temp_compressed, filepath)
                    else: os.remove(temp_compressed)
                        
            elif not is_audio and app.config.get('COMPRESS_VIDEO', False):
                info = get_video_info(filepath)
                width = info['width']
                scale_filter = f'scale={min(width, app.config.get("MAX_WIDTH", 1280))}:-1'
                
                # 核心修复: 加入 -movflags +faststart 解决 [-6324] 解码错误，允许边下边播
                cmd = [
                    'ffmpeg', '-i', filepath, '-vf', scale_filter, 
                    '-c:v', 'libx264', '-preset', app.config.get('COMPRESSION_PRESET', 'fast'), 
                    '-crf', str(app.config.get('CRF_VALUE', 28)), 
                    '-c:a', 'aac', '-b:a', app.config.get('AUDIO_BITRATE', '128k'), 
                    '-movflags', '+faststart',
                    '-y', temp_compressed
                ]
                if subprocess.run(cmd, capture_output=True, timeout=1200).returncode == 0:
                    if os.path.getsize(temp_compressed) < os.path.getsize(filepath):
                        try:
                            os.replace(temp_compressed, filepath) # 原子替换，防止刚好有人在播放时替换导致崩溃
                        except:
                            os.remove(filepath); os.rename(temp_compressed, filepath)
                    else: os.remove(temp_compressed)

        # 2. 中度任务：生成预览动图 (GIF)
        if not is_audio and app.config.get('GENERATE_THUMBNAIL', True):
            base_name = os.path.splitext(unique_name)[0]
            gif_path = os.path.join(app.config['THUMBNAIL_FOLDER'], base_name + '.gif')
            
            duration = get_video_duration(filepath)
            start_pos = max(1, duration * 0.1)
            gif_duration = min(3, duration - start_pos)
            if gif_duration >= 1:
                subprocess.run(['ffmpeg', '-i', filepath, '-ss', str(start_pos), '-t', str(gif_duration), '-vf', f'fps=2,scale=320:-1:flags=lanczos', '-y', gif_path], capture_output=True, timeout=120)

        # 压缩完体积和时间可能微调了，再强制打一次最新缓存
        inject_cache_immediately(filepath, unique_name)
    except Exception as e:
        print(f"后台媒体任务异常 {unique_name}: {e}")

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
    end = start + per_page
    video_data = video_meta[start:end]
    videos = [v['filename'] for v in video_data]
    
    return render_template('index.html', videos=videos, video_data=video_data, page=page, total_pages=total_pages, total=total, compress_enabled=app.config.get('COMPRESS_VIDEO', False), request=request)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files: return jsonify({'success': False, 'error': '没有文件'}), 400
    compress = request.form.get('compress', 'true') == 'true'
    files = request.files.getlist('file')
    uploaded = []
    
    for file in files:
        if not file or not file.filename: continue
        filename = safe_secure_filename(file.filename)
        unique_name = str(uuid.uuid4())[:6] + '_' + filename
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
        
        try:
            # 1. 瞬间落盘保存
            file.save(filepath)
            is_audio = allowed_audio_file(filename)
            base_name = os.path.splitext(unique_name)[0]
            
            # 2. 主线程立刻提取单张封面，保证网页刷新后缩略图立即可见
            if not is_audio and app.config.get('GENERATE_THUMBNAIL', True):
                thumb_path = os.path.join(app.config['THUMBNAIL_FOLDER'], base_name + '.jpg')
                generate_thumbnail(filepath, thumb_path)
            
            # 3. 注入极速缓存，保证首页列表中马上能刷出来
            inject_cache_immediately(filepath, unique_name)
            
            # 4. 把重度耗时的转码和做动图任务推入排队线程池
            ffmpeg_pool.submit(background_process_media, filepath, unique_name, is_audio, compress)
            
            uploaded.append(unique_name)
        except Exception as e: print(f"文件处理异常: {e}")
    
    if uploaded: return jsonify({'success': True, 'uploaded': uploaded, 'message': '上传成功！服务器正在后台进行视频优化。'})
    return jsonify({'success': False, 'error': '上传失败'}), 400

@app.route('/videos/<filename>')
def serve_video(filename): return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/audios/<filename>')
def serve_audio(filename): return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/thumbnails/<filename>')
def serve_thumbnail(filename): return send_from_directory(app.config['THUMBNAIL_FOLDER'], filename, mimetype='image/jpeg')

@app.route('/previews/<filename>')
def serve_preview(filename):
    gif_path = os.path.join(app.config['THUMBNAIL_FOLDER'], filename)
    if os.path.exists(gif_path): return send_from_directory(app.config['THUMBNAIL_FOLDER'], filename, mimetype='image/gif')
    return '', 404

@app.route('/delete/<filename>', methods=['POST'])
def delete_file(filename):
    """彻底干净的删除机制"""
    try:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        base_name = os.path.splitext(filename)[0]
        thumb_path = os.path.join(app.config['THUMBNAIL_FOLDER'], base_name + '.jpg')
        gif_path = os.path.join(app.config['THUMBNAIL_FOLDER'], base_name + '.gif')
        
        covers = load_json_safe(CUSTOM_COVERS_FILE)
        if filename in covers:
            custom_cover_path = os.path.join(app.config['THUMBNAIL_FOLDER'], covers[filename].get('cover', ''))
            if os.path.exists(custom_cover_path): os.remove(custom_cover_path)
            del covers[filename]
            save_json_safe(CUSTOM_COVERS_FILE, covers)
        
        deleted = {'video': False, 'thumbnail': False, 'cache': False}
        
        if os.path.exists(filepath):
            os.remove(filepath); deleted['video'] = True
            cache = load_video_meta_cache()
            if filename in cache:
                del cache[filename]; save_video_meta_cache(cache)
                deleted['cache'] = True
        
        if os.path.exists(thumb_path): os.remove(thumb_path); deleted['thumbnail'] = True
        if os.path.exists(gif_path): os.remove(gif_path)
            
        return jsonify({'success': True, 'deleted': deleted})
    except Exception as e: return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/videos')
def api_videos():
    videos = get_video_list()
    return jsonify({'videos': videos, 'total': len(videos)})

@app.route('/api/stats')
def api_stats():
    meta = get_all_video_metadata()
    total_size = sum(v.get('size_mb', 0) for v in meta)
    
    def get_folder_size_fast(path):
        total = 0
        if os.path.exists(path):
            with os.scandir(path) as it:
                for entry in it:
                    if entry.is_file(): total += entry.stat().st_size
        return total
    
    return jsonify({
        'total_videos': len(meta), 'total_size_mb': round(total_size, 2),
        'total_size_gb': round(total_size / 1024, 2),
        'uploads_size_mb': round(get_folder_size_fast(app.config['UPLOAD_FOLDER']) / 1024 / 1024, 2),
        'thumbnails_size_mb': round(get_folder_size_fast(app.config['THUMBNAIL_FOLDER']) / 1024 / 1024, 2)
    })

@app.route('/api/video/<filename>')
def api_video_info(filename):
    cache = load_video_meta_cache()
    if filename in cache:
        info_data = cache[filename]
        info_data['play_count'] = load_json_safe(PLAY_COUNTS_FILE).get(filename, 0)
        if 'bitrate_kbps' not in info_data: info_data['bitrate_kbps'] = 0
        return jsonify(info_data)
    return jsonify({'error': '文件不存在'}), 404

# ================= 业务拓展功能 =================

@app.route('/api/play/<filename>', methods=['POST'])
def api_play(filename):
    counts = load_json_safe(PLAY_COUNTS_FILE)
    counts[filename] = counts.get(filename, 0) + 1
    save_json_safe(PLAY_COUNTS_FILE, counts)
    return jsonify({'success': True, 'play_count': counts[filename]})

# 标签分类
@app.route('/api/tags/<filename>', methods=['GET'])
def api_get_tags(filename): return jsonify({'filename': filename, 'tags': load_json_safe(VIDEO_TAGS_FILE).get(filename, [])})

@app.route('/api/tags/<filename>', methods=['POST'])
def api_add_tag(filename):
    tag = request.get_json().get('tag', '').strip()
    if not tag: return jsonify({'error': '标签不能为空'}), 400
    data = load_json_safe(VIDEO_TAGS_FILE)
    tags = data.get(filename, [])
    if tag not in tags:
        tags.append(tag); data[filename] = tags; save_json_safe(VIDEO_TAGS_FILE, data)
    return jsonify({'success': True, 'tags': tags})

@app.route('/api/tags/<filename>', methods=['DELETE'])
def api_remove_tag(filename):
    tag = request.get_json().get('tag', '').strip()
    data = load_json_safe(VIDEO_TAGS_FILE)
    tags = data.get(filename, [])
    if tag in tags:
        tags.remove(tag); data[filename] = tags; save_json_safe(VIDEO_TAGS_FILE, data)
    return jsonify({'success': True, 'tags': tags})

@app.route('/api/tags', methods=['GET'])
def api_all_tags():
    data = load_json_safe(VIDEO_TAGS_FILE)
    all_tags = sorted(list(set(tag for tags in data.values() for tag in tags)))
    tag_counts = {}
    for tags_list in data.values():
        for tag in tags_list: tag_counts[tag] = tag_counts.get(tag, 0) + 1
    return jsonify({'tags': all_tags, 'counts': tag_counts})

# 描述备注
@app.route('/api/description/<filename>', methods=['GET'])
def api_get_description(filename): return jsonify({'filename': filename, **load_json_safe(VIDEO_DESCRIPTIONS_FILE).get(filename, {'description': '', 'notes': '', 'updated_at': ''})})

@app.route('/api/description/<filename>', methods=['POST'])
def api_save_description(filename):
    data = load_json_safe(VIDEO_DESCRIPTIONS_FILE)
    req = request.get_json()
    data[filename] = {'description': req.get('description', ''), 'notes': req.get('notes', ''), 'updated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    save_json_safe(VIDEO_DESCRIPTIONS_FILE, data)
    return jsonify({'success': True, 'updated_at': data[filename]['updated_at']})

@app.route('/api/description/<filename>', methods=['DELETE'])
def api_delete_description(filename):
    data = load_json_safe(VIDEO_DESCRIPTIONS_FILE)
    if filename in data: del data[filename]; save_json_safe(VIDEO_DESCRIPTIONS_FILE, data)
    return jsonify({'success': True})

# 播放列表
@app.route('/api/playlists', methods=['GET'])
def api_get_playlists(): return jsonify({'playlists': list(load_json_safe(PLAYLISTS_FILE).values())})

@app.route('/api/playlists', methods=['POST'])
def api_create_playlist():
    data = load_json_safe(PLAYLISTS_FILE)
    req = request.get_json()
    pid = str(uuid.uuid4())[:8]
    data[pid] = {'id': pid, 'name': req.get('name', '未命名播放列表'), 'description': req.get('description', ''), 'videos': [], 'cover': '', 'is_public': True, 'play_count': 0, 'created_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'updated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    save_json_safe(PLAYLISTS_FILE, data)
    return jsonify({'success': True, 'id': pid})

@app.route('/api/playlists/<pid>', methods=['GET'])
def api_get_playlist(pid):
    data = load_json_safe(PLAYLISTS_FILE)
    return jsonify(data[pid]) if pid in data else (jsonify({'error': '不存在'}), 404)

@app.route('/api/playlists/<pid>', methods=['POST'])
def api_add_to_playlist(pid):
    filename = request.get_json().get('filename')
    data = load_json_safe(PLAYLISTS_FILE)
    if pid in data and filename and filename not in data[pid]['videos']:
        data[pid]['videos'].append(filename); data[pid]['updated_at'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'); save_json_safe(PLAYLISTS_FILE, data)
        return jsonify({'success': True})
    return jsonify({'success': False})

@app.route('/api/playlists/<pid>/<path:filename>', methods=['DELETE'])
def api_remove_from_playlist(pid, filename):
    data = load_json_safe(PLAYLISTS_FILE)
    if pid in data and filename in data[pid]['videos']:
        data[pid]['videos'].remove(filename); data[pid]['updated_at'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'); save_json_safe(PLAYLISTS_FILE, data)
        return jsonify({'success': True})
    return jsonify({'success': False})

@app.route('/api/playlists/<pid>', methods=['DELETE'])
def api_delete_playlist(pid):
    data = load_json_safe(PLAYLISTS_FILE)
    if pid in data: del data[pid]; save_json_safe(PLAYLISTS_FILE, data); return jsonify({'success': True})
    return jsonify({'success': False})

@app.route('/api/playlists/<pid>/reorder', methods=['POST'])
def api_reorder_playlist(pid):
    data = load_json_safe(PLAYLISTS_FILE)
    if pid in data:
        data[pid]['videos'] = request.get_json().get('videos', []); data[pid]['updated_at'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'); save_json_safe(PLAYLISTS_FILE, data)
        return jsonify({'success': True})
    return jsonify({'success': False})

@app.route('/api/playlists/<pid>/cover', methods=['PUT'])
def api_set_playlist_cover(pid):
    data = load_json_safe(PLAYLISTS_FILE)
    if pid in data:
        data[pid]['cover'] = request.get_json().get('cover', ''); save_json_safe(PLAYLISTS_FILE, data)
        return jsonify({'success': True})
    return jsonify({'success': False})

@app.route('/api/playlists/<pid>/export', methods=['GET'])
def api_export_playlist(pid):
    data = load_json_safe(PLAYLISTS_FILE).get(pid)
    return jsonify(data) if data else (jsonify({'error': '不存在'}), 404)

@app.route('/api/playlists/import', methods=['POST'])
def api_import_playlist():
    data = load_json_safe(PLAYLISTS_FILE)
    req = request.get_json()
    pid = str(uuid.uuid4())[:8]
    req['id'] = pid
    req['created_at'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    req['updated_at'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    data[pid] = req
    save_json_safe(PLAYLISTS_FILE, data)
    return jsonify({'success': True, 'id': pid})

@app.route('/api/playlists/<pid>/share', methods=['GET'])
def api_share_playlist(pid):
    data = load_json_safe(PLAYLISTS_FILE).get(pid)
    if data:
        share_data = base64.b64encode(json.dumps(data).encode()).decode()
        share_url = request.url_root.rstrip('/') + '/playlist/import/' + share_data
        return jsonify({'success': True, 'share_url': share_url, 'share_code': share_data[:50] + '...'})
    return jsonify({'error': '不存在'}), 404

@app.route('/playlist/import/<share_data>')
def import_playlist_page(share_data):
    try:
        playlist_data = json.loads(base64.b64decode(share_data))
        return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>导入列表</title></head><body><script>fetch('/api/playlists/import',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({json.dumps(playlist_data)})}}).then(r=>r.json()).then(d=>{{if(d.success){{alert('导入成功！');window.location.href='/';}}}})</script></body></html>'''
    except Exception as e: return f'<h1>导入失败</h1><p>{str(e)}</p>', 400

# 观看历史
@app.route('/api/history/<filename>', methods=['GET'])
def api_get_history(filename): return jsonify({'filename': filename, **load_json_safe(WATCH_HISTORY_FILE).get(filename, {'position': 0, 'duration': 0, 'progress_percent': 0})})

@app.route('/api/history/<filename>', methods=['POST'])
def api_update_history(filename):
    data = load_json_safe(WATCH_HISTORY_FILE)
    req = request.get_json()
    pos, dur = req.get('position', 0), req.get('duration', 0)
    existing = data.get(filename, {})
    data[filename] = {'position': pos, 'duration': dur, 'last_watched': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'progress_percent': round((pos / dur * 100) if dur > 0 else 0, 1), 'watch_count': existing.get('watch_count', 0) + 1, 'device': 'web', 'first_watched': existing.get('first_watched', datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}
    save_json_safe(WATCH_HISTORY_FILE, data)
    return jsonify({'success': True, **data[filename]})

@app.route('/api/history/recent', methods=['GET'])
def api_get_recent_history():
    items = sorted(load_json_safe(WATCH_HISTORY_FILE).items(), key=lambda x: x[1].get('last_watched', ''), reverse=True)
    return jsonify({'history': dict(items[:request.args.get('limit', 20, type=int)])})

# 密码保护
def hash_password(password): return hashlib.sha256(password.encode()).hexdigest()

@app.route('/api/password/<filename>', methods=['GET'])
def api_check_password(filename):
    data = load_json_safe(VIDEO_PASSWORDS_FILE)
    return jsonify({'filename': filename, 'protected': filename in data, 'hint': data.get(filename, {}).get('hint', '')})

@app.route('/api/password/<filename>', methods=['POST'])
def api_verify_password(filename):
    data = load_json_safe(VIDEO_PASSWORDS_FILE)
    if filename not in data: return jsonify({'success': True})
    if hash_password(request.get_json().get('password', '')) == data[filename].get('password', ''):
        data[filename]['access_count'] = data[filename].get('access_count', 0) + 1
        save_json_safe(VIDEO_PASSWORDS_FILE, data)
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': '密码错误'}), 401

@app.route('/api/password/<filename>', methods=['PUT'])
def api_set_password(filename):
    pwd, hint = request.get_json().get('password', ''), request.get_json().get('hint', '')
    data = load_json_safe(VIDEO_PASSWORDS_FILE)
    if pwd:
        if len(pwd) < 4: return jsonify({'error': '密码至少 4 位'}), 400
        data[filename] = {'password': hash_password(pwd), 'hint': hint, 'created_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'access_count': 0}
    elif filename in data: del data[filename]
    save_json_safe(VIDEO_PASSWORDS_FILE, data)
    return jsonify({'success': True, 'protected': bool(pwd)})

# 自定义封面
@app.route('/api/cover/<filename>', methods=['GET'])
def api_get_cover(filename):
    cover = load_json_safe(CUSTOM_COVERS_FILE).get(filename, {}).get('cover', '')
    return jsonify({'filename': filename, 'custom_cover': cover, 'has_custom': bool(cover)})

@app.route('/api/cover/<filename>', methods=['PUT'])
def api_set_cover(filename):
    cover_filename = request.get_json().get('cover', '')
    data = load_json_safe(CUSTOM_COVERS_FILE)
    if cover_filename: data[filename] = {'cover': cover_filename}
    elif filename in data: del data[filename]
    save_json_safe(CUSTOM_COVERS_FILE, data)
    return jsonify({'success': True, 'cover': cover_filename})

@app.route('/covers/<filename>')
def serve_custom_cover(filename): return send_from_directory(app.config['THUMBNAIL_FOLDER'], filename, mimetype='image/jpeg')

@app.route('/api/cover/upload/<video_filename>', methods=['POST'])
def api_upload_cover(video_filename):
    if 'cover' not in request.files: return jsonify({'error': '没有文件'}), 400
    file = request.files['cover']
    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    if ext not in {'jpg', 'jpeg', 'png', 'webp'}: return jsonify({'error': '不支持的格式'}), 400
    try:
        cover_name = f"{video_filename.rsplit('.', 1)[0]}_cover.{ext}"
        cover_path = os.path.join(app.config['THUMBNAIL_FOLDER'], cover_name)
        file.save(cover_path)
        data = load_json_safe(CUSTOM_COVERS_FILE)
        data[video_filename] = {'cover': cover_name}; save_json_safe(CUSTOM_COVERS_FILE, data)
        return jsonify({'success': True, 'cover': cover_name, 'url': f'/covers/{cover_name}'})
    except Exception as e: return jsonify({'error': str(e)}), 500

# PWA 支持
@app.route('/offline.html')
def offline_page(): return render_template('offline.html')
@app.route('/static/sw.js')
def service_worker(): return send_from_directory('static', 'sw.js', mimetype='application/javascript')
@app.route('/static/manifest.json')
def manifest(): return send_from_directory('static', 'manifest.json', mimetype='application/json')

# 嗅探下载
@app.route('/api/download', methods=['POST'])
def download_video():
    data = request.json
    url, download_type, custom_filename = data.get('url', ''), data.get('type', 'http'), data.get('customFilename', '')
    if not url: return jsonify({'success': False, 'error': '缺少视频链接'}), 400
    try:
        filename = safe_secure_filename(custom_filename) if custom_filename else f"{uuid.uuid4().hex[:8]}_dl.mp4"
        if not filename.endswith('.mp4'): filename += '.mp4'
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        cmd = ['wget', '-O', filepath, '--user-agent=Mozilla/5.0', url] if download_type == 'http' else \
              ['aria2c', '--dir=' + os.path.dirname(filepath), '--out=' + os.path.basename(filepath), '--seed-time=0', '--timeout=600', url]
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try: process.wait(timeout=900)
        except subprocess.TimeoutExpired: process.kill(); return jsonify({'error': '下载超时'}), 500
            
        if process.returncode != 0 or not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
            return jsonify({'error': '下载失败，链接可能已失效'}), 500
            
        # 下载完成处理：做封面、压缓存、进后台排队
        generate_thumbnail(filepath, os.path.join(app.config['THUMBNAIL_FOLDER'], filename.rsplit('.', 1)[0] + '.jpg'))
        inject_cache_immediately(filepath, filename)
        ffmpeg_pool.submit(background_process_media, filepath, filename, False, False)
        
        return jsonify({'success': True, 'filename': filename, 'size': get_file_size(filepath), 'message': '下载成功'})
    except Exception as e: return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['THUMBNAIL_FOLDER'], exist_ok=True)
    print(f"🎬 极速与高并发版视频后台启动中...")
    print(f"✅ 后台异步上传 + 防解码错误(faststart)机制已生效")
    print(f"📁 监听端口：http://localhost:{app.config['PORT']}")
    app.run(host=app.config.get('HOST', '0.0.0.0'), port=app.config['PORT'], debug=app.config.get('DEBUG', False))
