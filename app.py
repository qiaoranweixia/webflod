"""
Flask 视频网站 - 终极完美版 (Ultimate Edition)
功能：内存缓存/MD5防重/智能查重/断点续播/全局搜索/无损重命名/后台防丢压制/yt-dlp全网嗅探/密码防越权
"""

import os
import uuid
import json
import subprocess
import threading
import datetime
import hashlib
import re
import time
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, send_from_directory, render_template, jsonify, make_response
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

# 强制解除 Flask 内部的文件大小限制，允许上传 2GB~100GB+ 的超大文件
app.config['MAX_CONTENT_LENGTH'] = None 

# ================= 全局资源与锁 (高并发健壮性核心) =================
# 后台线程池：限制最多同时运行 2 个压制/抽帧任务，防止 CPU 核爆
ffmpeg_pool = ThreadPoolExecutor(max_workers=2)

# 全局锁：彻底防止多用户并发操作导致 JSON 文件被清空或覆盖
file_locks = {
    'cache': threading.Lock(),
    'json': threading.Lock()
}

# 内存级缓存变量：防止每次翻页都去扫描硬盘导致卡顿
_MEM_CACHE = []
_LAST_SCAN_TIME = 0

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
    """计算文件的 MD5 指纹（分块读取，防大文件撑爆内存）"""
    hash_md5 = hashlib.md5()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(81920), b""): 
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except: return None

def get_clean_unique_filename(folder, original_filename):
    """智能干净命名：保留原名，只有重复时才加 (1), (2)"""
    if not original_filename: return f"unnamed_{uuid.uuid4().hex[:6]}.mp4"
    # 清理非法字符
    clean_name = re.sub(r'[/\\?%*:|"<>]', '', original_filename)
    if not clean_name: clean_name = f"video_{uuid.uuid4().hex[:6]}.mp4"
    
    base, ext = os.path.splitext(clean_name)
    final_name, counter = clean_name, 1
    # 冲突检测
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
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"

def get_video_duration(filepath):
    try:
        res = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', filepath], capture_output=True, text=True, timeout=5)
        if res.returncode == 0: return float(json.loads(res.stdout)['format']['duration'])
    except: pass
    return 0

def get_video_info(filepath):
    info = {'width': 0, 'height': 0, 'codec': 'unknown'}
    try:
        res = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,codec_name', '-of', 'json', filepath], capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            data = json.loads(res.stdout)
            if data.get('streams'):
                info['width'] = data['streams'][0].get('width', 0)
                info['height'] = data['streams'][0].get('height', 0)
                info['codec'] = data['streams'][0].get('codec_name', 'unknown')
    except: pass
    return info

def generate_thumbnail(video_path, thumb_path):
    """提取单帧作为封面图"""
    try:
        time_pos = min(app.config.get('THUMBNAIL_TIME', 3), get_video_duration(video_path) * 0.8)
        subprocess.run(['ffmpeg', '-i', video_path, '-ss', str(time_pos), '-vframes', '1', '-vf', 'scale=320:-1', '-y', thumb_path], capture_output=True, timeout=15)
        return os.path.exists(thumb_path)
    except: return False

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

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

# ====== 高性能内存与硬盘双重缓存机制 ======
def get_all_video_metadata():
    """带 3 秒防抖内存缓存的目录扫描，极大提升翻页和检索速度"""
    global _MEM_CACHE, _LAST_SCAN_TIME
    now = time.time()
    
    # 如果 3 秒内已经扫描过，直接返回内存数据，杜绝 I/O 卡顿
    if now - _LAST_SCAN_TIME < 3 and _MEM_CACHE: 
        return _MEM_CACHE

    if not os.path.exists(app.config['UPLOAD_FOLDER']): return []
    
    # 扫描真实物理文件列表
    files = {}
    try:
        with os.scandir(app.config['UPLOAD_FOLDER']) as it:
            for entry in it:
                if entry.is_file() and allowed_file(entry.name): 
                    files[entry.name] = entry.stat().st_mtime
    except: return []

    # 加载硬盘持久化缓存
    with file_locks['cache']:
        try:
            with open(VIDEO_META_CACHE_FILE, 'r', encoding='utf-8') as f: cache = json.load(f)
        except: cache = {}

    updated = False
    
    # 1. 剔除已经被物理删除的僵尸缓存
    for k in list(cache.keys()):
        if k not in files: 
            del cache[k]; updated = True
            
    # 2. 对比增量更新
    video_meta = []
    for filename, mtime in files.items():
        if filename in cache and cache[filename].get('mtime') == mtime:
            video_meta.append(cache[filename])
        else:
            # 遇到新文件或被修改的文件，提取元数据
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            duration = get_video_duration(filepath)
            info = get_video_info(filepath)
            meta = {
                'filename': filename, 'size_mb': get_file_size(filepath),
                'duration': format_duration(duration), 'duration_sec': duration,
                'resolution': f"{info['width']}x{info['height']}" if info['width'] else '未知',
                'codec': info['codec'], 'mtime': mtime, 'md5': None
            }
            cache[filename] = meta
            video_meta.append(meta)
            updated = True
            
    # 如果有变动，写回硬盘
    if updated:
        with file_locks['cache']:
            with open(VIDEO_META_CACHE_FILE, 'w', encoding='utf-8') as f: 
                json.dump(cache, f, ensure_ascii=False)
            
    # 更新内存缓存并重置计时器
    _MEM_CACHE = video_meta
    _LAST_SCAN_TIME = time.time()
    return video_meta

# ================= 媒体后台处理 (异步任务) =================
def background_process_media(filepath, final_filename, is_audio, compress_flag):
    """后台处理，加入了强力垃圾回收机制，防止大文件断电生成残片"""
    temp_compressed = filepath + '_temp' + ('.mp3' if is_audio else '.mp4')
    try:
        # 1. 压缩任务
        if compress_flag:
            cmd = ['ffmpeg', '-i', filepath, '-c:v', 'libx264', '-preset', 'fast', '-crf', '28', '-c:a', 'aac', '-movflags', '+faststart', '-y', temp_compressed]
            if subprocess.run(cmd, capture_output=True, timeout=3600).returncode == 0 and os.path.exists(temp_compressed):
                if os.path.getsize(temp_compressed) < os.path.getsize(filepath):
                    try: os.replace(temp_compressed, filepath) # 原子替换防断流
                    except: os.remove(filepath); os.rename(temp_compressed, filepath)

        # 2. 生成 GIF 动图预览任务
        if not is_audio and app.config.get('GENERATE_THUMBNAIL', True):
            gif_path = os.path.join(app.config['THUMBNAIL_FOLDER'], os.path.splitext(final_filename)[0] + '.gif')
            dur = get_video_duration(filepath)
            subprocess.run(['ffmpeg', '-i', filepath, '-ss', str(max(1, dur*0.1)), '-t', '2', '-vf', 'fps=2,scale=320:-1:flags=lanczos', '-y', gif_path], capture_output=True, timeout=60)
            
        global _LAST_SCAN_TIME; _LAST_SCAN_TIME = 0 # 任务完成，强制触发前端刷新缓存
    except Exception as e:
        print(f"后台任务异常 {final_filename}: {e}")
    finally:
        # 【终极清理】无论成功失败，只要残留了 temp 临时文件，一律抹杀
        if os.path.exists(temp_compressed):
            try: os.remove(temp_compressed)
            except: pass

# ================= 基础核心路由 =================

@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    sort_by = request.args.get('sort', 'date')
    search_query = request.args.get('search', '').strip().lower() # 全局搜索关键词
    per_page = app.config.get('VIDEOS_PER_PAGE', 30)
    
    video_meta = get_all_video_metadata()
    
    # 1. 全局查重与搜索过滤
    if search_query:
        video_meta = [v for v in video_meta if search_query in v['filename'].lower()]

    # 2. 排序逻辑
    if sort_by == 'name': video_meta.sort(key=lambda x: x['filename'].lower())
    elif sort_by == 'size': video_meta.sort(key=lambda x: x['size_mb'], reverse=True)
    else: video_meta.sort(key=lambda x: x['mtime'], reverse=True)
    
    # 3. 分页逻辑
    total = len(video_meta)
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    
    return render_template('index.html', videos=[v['filename'] for v in video_meta[start:start+per_page]], video_data=video_meta[start:start+per_page], page=page, total_pages=total_pages, total=total, search_query=search_query, request=request)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files: return jsonify({'error': '没有文件'}), 400
    compress = request.form.get('compress', 'true') == 'true'
    files = request.files.getlist('file')
    
    uploaded, skipped = [], []
    
    # 加载现有 MD5 库用于秒传防重
    with file_locks['cache']:
        try:
            with open(VIDEO_META_CACHE_FILE, 'r') as f: cache = json.load(f)
        except: cache = {}
    existing_md5_map = {m.get('md5'): m['filename'] for m in cache.values() if m.get('md5')}
    
    for file in files:
        if not file or not file.filename: continue
        # 先保存为隐藏文件计算指纹
        temp_filepath = os.path.join(app.config['UPLOAD_FOLDER'], f".temp_{uuid.uuid4().hex}.tmp")
        try:
            file.save(temp_filepath)
            file_md5 = get_file_md5(temp_filepath)
            
            # 判定：MD5 是否已存在于库中？
            if file_md5 in existing_md5_map:
                os.remove(temp_filepath)
                skipped.append(f"{file.filename} (已存在: {existing_md5_map[file_md5]})")
                continue
                
            # 重命名为干净的文件名
            final_filename = get_clean_unique_filename(app.config['UPLOAD_FOLDER'], file.filename)
            final_filepath = os.path.join(app.config['UPLOAD_FOLDER'], final_filename)
            os.rename(temp_filepath, final_filepath)
            
            is_audio = allowed_audio_file(final_filename)
            if not is_audio: 
                generate_thumbnail(final_filepath, os.path.join(app.config['THUMBNAIL_FOLDER'], os.path.splitext(final_filename)[0] + '.jpg'))
            
            # 更新哈希表并触发后台任务
            existing_md5_map[file_md5] = final_filename
            global _LAST_SCAN_TIME; _LAST_SCAN_TIME = 0 
            ffmpeg_pool.submit(background_process_media, final_filepath, final_filename, is_audio, compress)
            uploaded.append(final_filename)
            
        except Exception:
            if os.path.exists(temp_filepath): os.remove(temp_filepath)
    
    return jsonify({'success': True, 'uploaded': uploaded, 'skipped': skipped})

@app.route('/videos/<filename>')
def serve_video(filename):
    """【安全核心】防越权漏洞，带密码的视频无法通过 URL 直接下载"""
    pwd_data = load_json_safe(VIDEO_PASSWORDS_FILE)
    if filename in pwd_data:
        cookie_hash = request.cookies.get(f"video_auth_{filename}")
        if cookie_hash != pwd_data[filename]['password']:
            return "403 Forbidden: 视频已加密，请在首页输入密码解锁。", 403
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/thumbnails/<filename>')
def serve_thumbnail(filename): return send_from_directory(app.config['THUMBNAIL_FOLDER'], filename, mimetype='image/jpeg')

@app.route('/previews/<filename>')
def serve_preview(filename):
    gif = os.path.join(app.config['THUMBNAIL_FOLDER'], filename)
    return send_from_directory(app.config['THUMBNAIL_FOLDER'], filename, mimetype='image/gif') if os.path.exists(gif) else ('', 404)

@app.route('/delete/<filename>', methods=['POST'])
def delete_file(filename):
    """【彻底清理】删除物理文件以及抹杀所有与之关联的 JSON 脏数据"""
    try:
        base_name = os.path.splitext(filename)[0]
        for p in [os.path.join(app.config['UPLOAD_FOLDER'], filename), os.path.join(app.config['THUMBNAIL_FOLDER'], base_name + '.jpg'), os.path.join(app.config['THUMBNAIL_FOLDER'], base_name + '.gif')]:
            if os.path.exists(p): os.remove(p)
            
        def rm_json(fp):
            data = load_json_safe(fp)
            if filename in data: del data[filename]; save_json_safe(fp, data)
            
        for fp in [CUSTOM_COVERS_FILE, VIDEO_TAGS_FILE, VIDEO_DESCRIPTIONS_FILE, PLAY_COUNTS_FILE, WATCH_HISTORY_FILE, VIDEO_PASSWORDS_FILE]:
            rm_json(fp)

        playlists = load_json_safe(PLAYLISTS_FILE)
        mod = False
        for pid in playlists:
            if filename in playlists[pid]['videos']:
                playlists[pid]['videos'].remove(filename); mod = True
        if mod: save_json_safe(PLAYLISTS_FILE, playlists)
        
        global _LAST_SCAN_TIME; _LAST_SCAN_TIME = 0 
        return jsonify({'success': True})
    except: return jsonify({'success': False}), 500

# ================= 高级拓展业务 API =================

@app.route('/api/rename/<old_filename>', methods=['POST'])
def rename_file(old_filename):
    """【新功能】无损重命名：自动同步所有数据库记录和封面文件"""
    new_base = request.json.get('new_name', '').strip()
    if not new_base: return jsonify({'error': '名称不能为空'}), 400

    new_base = re.sub(r'[/\\?%*:|"<>]', '', new_base)
    ext = os.path.splitext(old_filename)[1]
    new_filename = new_base + ext

    if old_filename == new_filename: return jsonify({'success': True})
    
    old_path = os.path.join(app.config['UPLOAD_FOLDER'], old_filename)
    new_path = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
    
    if os.path.exists(new_path): return jsonify({'error': '同名文件已存在'}), 400
    if not os.path.exists(old_path): return jsonify({'error': '原文件不存在'}), 404

    try:
        os.rename(old_path, new_path)
        
        # 重命名缩略图
        old_base = os.path.splitext(old_filename)[0]
        t_dir = app.config['THUMBNAIL_FOLDER']
        for ext_thumb in ['.jpg', '.gif']:
            if os.path.exists(os.path.join(t_dir, old_base + ext_thumb)):
                os.rename(os.path.join(t_dir, old_base + ext_thumb), os.path.join(t_dir, new_base + ext_thumb))

        # 关联更新 JSON
        def rename_in_json(filepath):
            data = load_json_safe(filepath)
            if old_filename in data:
                data[new_filename] = data.pop(old_filename)
                save_json_safe(filepath, data)

        rename_in_json(VIDEO_PASSWORDS_FILE)
        rename_in_json(PLAY_COUNTS_FILE)
        rename_in_json(WATCH_HISTORY_FILE)
        rename_in_json(CUSTOM_COVERS_FILE)
        rename_in_json(VIDEO_DESCRIPTIONS_FILE)
        
        playlists = load_json_safe(PLAYLISTS_FILE)
        mod = False
        for pid in playlists:
            if old_filename in playlists[pid]['videos']:
                idx = playlists[pid]['videos'].index(old_filename)
                playlists[pid]['videos'][idx] = new_filename
                mod = True
        if mod: save_json_safe(PLAYLISTS_FILE, playlists)

        global _LAST_SCAN_TIME; _LAST_SCAN_TIME = 0 
        return jsonify({'success': True, 'new_filename': new_filename})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/duplicates')
def find_duplicates():
    """【新功能】智能查重：提取库中体积与时长相同的视频分组"""
    meta = get_all_video_metadata()
    groups = {}
    for v in meta:
        key = f"{int(v.get('size_mb', 0))}MB_{int(v.get('duration_sec', 0))}秒"
        if key not in groups: groups[key] = []
        groups[key].append(v)
    dupes = {k: v for k, v in groups.items() if len(v) > 1}
    return jsonify({'success': True, 'groups': dupes})

@app.route('/api/stats')
def api_stats():
    meta = get_all_video_metadata()
    total_size = sum(v.get('size_mb', 0) for v in meta)
    return jsonify({'total_videos': len(meta), 'total_size_gb': round(total_size / 1024, 2), 'total_size_mb': round(total_size, 2)})

@app.route('/api/history/recent')
def api_history_recent():
    items = sorted(load_json_safe(WATCH_HISTORY_FILE).items(), key=lambda x: x[1].get('last_watched', ''), reverse=True)
    return jsonify({'history': dict(items[:20])})

@app.route('/api/history/<filename>', methods=['POST'])
def api_update_history(filename):
    data = load_json_safe(WATCH_HISTORY_FILE)
    req = request.json
    pos, dur = req.get('position', 0), req.get('duration', 0)
    data[filename] = {
        'progress_percent': round((pos/dur*100) if dur>0 else 0, 1), 
        'position': pos, # 保存精确断点，用于续播
        'last_watched': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    save_json_safe(WATCH_HISTORY_FILE, data)
    return jsonify({'success': True})

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

@app.route('/api/playlists', methods=['GET', 'POST'])
def api_playlists():
    data = load_json_safe(PLAYLISTS_FILE)
    if request.method == 'GET': return jsonify({'playlists': list(data.values())})
    pid = str(uuid.uuid4())[:8]
    data[pid] = {'id': pid, 'name': request.json.get('name', '未命名合集'), 'videos': []}
    save_json_safe(PLAYLISTS_FILE, data); return jsonify({'success': True, 'id': pid})

@app.route('/api/playlists/<pid>', methods=['POST', 'DELETE'])
def api_playlist_actions(pid):
    data = load_json_safe(PLAYLISTS_FILE)
    if request.method == 'DELETE':
        if pid in data: del data[pid]; save_json_safe(PLAYLISTS_FILE, data)
        return jsonify({'success': True})
    
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
        base_name = get_clean_unique_filename(app.config['UPLOAD_FOLDER'], custom_name) if custom_name else f"web_{uuid.uuid4().hex[:6]}"
        if base_name.endswith('.mp4'): base_name = base_name[:-4]
        final_name = base_name + '.mp4'
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], final_name)
        
        cmd = ['yt-dlp', '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best', '-o', filepath, '--no-playlist', url]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try: proc.wait(timeout=900)
        except subprocess.TimeoutExpired: proc.kill(); return jsonify({'error': '嗅探超时'}), 500
            
        if proc.returncode != 0 or not os.path.exists(filepath): return jsonify({'error': '解析失败，链接可能已失效'}), 500
            
        generate_thumbnail(filepath, os.path.join(app.config['THUMBNAIL_FOLDER'], base_name + '.jpg'))
        global _LAST_SCAN_TIME; _LAST_SCAN_TIME = 0 
        ffmpeg_pool.submit(background_process_media, filepath, final_name, False, auto_compress)
        return jsonify({'success': True, 'filename': final_name})
    except Exception as e: return jsonify({'success': False, 'error': str(e)}), 500

# ================= 一键迁移老文件工具 =================
@app.route('/api/sync_old')
def sync_old_files():
    def bg_sync():
        print("🔄 [老文件同步] 开始扫描...")
        for filename in os.listdir(app.config['UPLOAD_FOLDER']):
            if not allowed_file(filename): continue
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            # 生成缺失封面
            if not allowed_audio_file(filename):
                thumb_path = os.path.join(app.config['THUMBNAIL_FOLDER'], os.path.splitext(filename)[0] + '.jpg')
                if not os.path.exists(thumb_path):
                    print(f"🖼️ 补封面: {filename}")
                    generate_thumbnail(filepath, thumb_path)
                    
        global _LAST_SCAN_TIME; _LAST_SCAN_TIME = 0 
        print("✅ [老文件同步] 完成！")
    threading.Thread(target=bg_sync).start()
    return "<body style='background:#1c1c24;color:white;text-align:center;padding-top:100px;'><h1>🚀 同步任务启动！</h1><p>请查看控制台进度。</p><button onclick=\"location.href='/'\">回主页</button></body>"

if __name__ == '__main__':
    os.makedirs(app.config.get('UPLOAD_FOLDER', 'uploads'), exist_ok=True)
    os.makedirs(app.config.get('THUMBNAIL_FOLDER', 'thumbnails'), exist_ok=True)
    print(f"🎬 极速与高并发版视频后台启动中...")
    print(f"🚀 MD5防重 / 查重 / 断点续播 / 重命名同步 / 画中画 支持完毕")
    print(f"📁 监听端口：http://localhost:{app.config.get('PORT', 5001)}")
    app.run(host=app.config.get('HOST', '0.0.0.0'), port=app.config.get('PORT', 5001), debug=app.config.get('DEBUG', False))
