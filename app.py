"""
Flask 视频网站 - 主应用
功能：上传/压缩/存储/在线播放/列表/删除/搜索/播放列表
端口：5001
"""

import os
import uuid
import json
import subprocess
from flask import Flask, request, redirect, url_for, send_from_directory, render_template, jsonify
from werkzeug.utils import secure_filename
from config import Config

app = Flask(__name__)
app.config.from_object(Config)


def allowed_file(filename):
    """验证文件是否为允许的视频格式"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def get_video_list():
    """获取视频目录中的所有视频文件列表（按修改时间倒序）"""
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        return []
    
    files = [f for f in os.listdir(app.config['UPLOAD_FOLDER']) if allowed_file(f)]
    files.sort(key=lambda x: os.path.getmtime(os.path.join(app.config['UPLOAD_FOLDER'], x)), reverse=True)
    return files


def get_file_size(filepath):
    """获取文件大小（MB）"""
    if os.path.exists(filepath):
        return round(os.path.getsize(filepath) / 1024 / 1024, 1)
    return 0


def get_video_duration(filepath):
    """获取视频时长（秒）"""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', filepath],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return float(json.loads(result.stdout)['format']['duration'])
    except:
        pass
    return 0


def format_duration(seconds):
    """格式化时长为 MM:SS"""
    if not seconds:
        return "未知"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"


def get_video_info(filepath):
    """获取视频详细信息（分辨率、编码等）"""
    info = {
        'width': 0,
        'height': 0,
        'codec': 'unknown',
        'bitrate': 0
    }
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0', 
             '-show_entries', 'stream=width,height,codec_name,bit_rate', '-of', 'json', filepath],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if data.get('streams'):
                stream = data['streams'][0]
                info['width'] = stream.get('width', 0)
                info['height'] = stream.get('height', 0)
                info['codec'] = stream.get('codec_name', 'unknown')
                info['bitrate'] = int(stream.get('bit_rate', 0) or 0)
    except:
        pass
    return info


def compress_video(input_path, output_path):
    """
    压缩视频文件
    返回：(成功布尔值，原始大小 MB, 压缩后大小 MB, 消息)
    """
    try:
        original_size = os.path.getsize(input_path)
        
        # 获取原视频信息
        info = get_video_info(input_path)
        width = info['width']
        height = info['height']
        
        # 计算缩放比例
        scale_filter = f'scale={min(width, app.config["MAX_WIDTH"])}:-1'
        
        # 构建 ffmpeg 命令
        cmd = [
            'ffmpeg',
            '-i', input_path,
            '-vf', scale_filter,
            '-c:v', 'libx264',
            '-preset', app.config['COMPRESSION_PRESET'],
            '-crf', str(app.config['CRF_VALUE']),
            '-c:a', 'aac',
            '-b:a', app.config['AUDIO_BITRATE'],
            '-y',  # 覆盖输出文件
            output_path
        ]
        
        # 执行压缩
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        
        if result.returncode == 0 and os.path.exists(output_path):
            compressed_size = os.path.getsize(output_path)
            original_mb = round(original_size / 1024 / 1024, 1)
            compressed_mb = round(compressed_size / 1024 / 1024, 1)
            ratio = round((1 - compressed_size / original_size) * 100, 1)
            
            return True, original_mb, compressed_mb, f"压缩成功！减小 {ratio}%"
        else:
            return False, 0, 0, "压缩失败"
            
    except subprocess.TimeoutExpired:
        return False, 0, 0, "压缩超时"
    except Exception as e:
        return False, 0, 0, f"压缩错误：{str(e)}"


def generate_thumbnail(video_path, thumb_path):
    """生成视频缩略图"""
    try:
        duration = get_video_duration(video_path)
        time_pos = min(app.config['THUMBNAIL_TIME'], duration * 0.8)
        
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-ss', str(time_pos),
            '-vframes', '1',
            '-vf', 'scale=320:-1',
            '-y',
            thumb_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        return result.returncode == 0
    except:
        return False


def generate_preview_gif(video_path, gif_path):
    """生成视频预览 GIF（3 秒，2fps）"""
    try:
        duration = get_video_duration(video_path)
        # 从视频 10% 位置开始，截取 3 秒
        start_pos = max(1, duration * 0.1)
        gif_duration = min(3, duration - start_pos)
        
        if gif_duration < 1:
            return False
        
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-ss', str(start_pos),
            '-t', str(gif_duration),
            '-vf', f'fps=2,scale=320:-1:flags=lanczos',
            '-y',
            gif_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        return result.returncode == 0 and os.path.exists(gif_path)
    except Exception as e:
        print(f"GIF 生成失败：{e}")
        return False


@app.route('/')
def index():
    """主页 - 显示视频列表（支持分页和排序）"""
    page = request.args.get('page', 1, type=int)
    sort_by = request.args.get('sort', 'date')
    per_page = app.config['VIDEOS_PER_PAGE']
    
    all_videos = get_video_list()
    
    # 获取所有视频元数据用于排序
    video_meta = []
    for video in all_videos:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], video)
        if os.path.exists(filepath):
            duration = get_video_duration(filepath)
            info = get_video_info(filepath)
            video_meta.append({
                'filename': video,
                'size_mb': get_file_size(filepath),
                'duration_sec': duration,
                'mtime': os.path.getmtime(filepath)
            })
    
    # 排序
    if sort_by == 'name':
        video_meta.sort(key=lambda x: x['filename'].lower())
    elif sort_by == 'size':
        video_meta.sort(key=lambda x: x['size_mb'], reverse=True)
    elif sort_by == 'duration':
        video_meta.sort(key=lambda x: x['duration_sec'], reverse=True)
    else:  # date
        video_meta.sort(key=lambda x: x['mtime'], reverse=True)
    
    all_videos = [v['filename'] for v in video_meta]
    
    total = len(all_videos)
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    end = start + per_page
    videos = all_videos[start:end]
    
    # 获取分页后视频的完整元数据
    video_data = []
    for video in videos:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], video)
        duration = get_video_duration(filepath)
        info = get_video_info(filepath)
        video_data.append({
            'filename': video,
            'size_mb': get_file_size(filepath),
            'duration': format_duration(duration),
            'duration_sec': duration,
            'resolution': f"{info['width']}x{info['height']}" if info['width'] else '未知',
            'codec': info['codec']
        })
    
    return render_template('index.html', 
                          videos=videos,
                          video_data=video_data,
                          page=page,
                          total_pages=total_pages,
                          total=total,
                          compress_enabled=app.config['COMPRESS_VIDEO'],
                          request=request)


@app.route('/upload', methods=['POST'])
def upload_file():
    """文件上传处理（带压缩选项）"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '没有文件'}), 400
    
    compress = request.form.get('compress', 'true') == 'true'
    files = request.files.getlist('file')
    uploaded = []
    compression_results = []
    
    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            unique_name = str(uuid.uuid4())[:8] + '_' + filename
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
            
            # 保存文件
            file.save(filepath)
            
            # 压缩处理
            if compress and app.config['COMPRESS_VIDEO']:
                compressed_path = filepath + '.compressed.mp4'
                success, orig_size, comp_size, msg = compress_video(filepath, compressed_path)
                
                if success and comp_size < orig_size:
                    # 保留压缩后的文件
                    os.remove(filepath)
                    os.rename(compressed_path, filepath)
                    compression_results.append({
                        'filename': unique_name,
                        'original': orig_size,
                        'compressed': comp_size,
                        'saved': round((1 - comp_size/orig_size) * 100, 1)
                    })
                else:
                    if os.path.exists(compressed_path):
                        os.remove(compressed_path)
                    compression_results.append({
                        'filename': unique_name,
                        'skipped': True,
                        'reason': msg
                    })
            
            # 生成缩略图
            if app.config['GENERATE_THUMBNAIL']:
                thumb_name = os.path.splitext(unique_name)[0] + '.jpg'
                thumb_path = os.path.join(app.config['THUMBNAIL_FOLDER'], thumb_name)
                generate_thumbnail(filepath, thumb_path)
            
            # 生成预览 GIF（异步，不阻塞上传）
            if app.config['GENERATE_THUMBNAIL']:
                try:
                    gif_name = os.path.splitext(unique_name)[0] + '.gif'
                    gif_path = os.path.join(app.config['THUMBNAIL_FOLDER'], gif_name)
                    # 在后台生成，不等待完成
                    import threading
                    threading.Thread(target=generate_preview_gif, args=(filepath, gif_path), daemon=True).start()
                except Exception as e:
                    print(f"GIF 生成线程失败：{e}")
            
            uploaded.append(unique_name)
    
    if uploaded:
        return jsonify({
            'success': True, 
            'uploaded': uploaded,
            'compression': compression_results if compress else None
        })
    return jsonify({'success': False, 'error': '没有成功上传的文件'}), 400


@app.route('/videos/<filename>')
def serve_video(filename):
    """视频文件服务"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/thumbnails/<filename>')
def serve_thumbnail(filename):
    """缩略图服务"""
    return send_from_directory(app.config['THUMBNAIL_FOLDER'], filename, mimetype='image/jpeg')


@app.route('/previews/<filename>')
def serve_preview(filename):
    """视频预览 GIF 服务"""
    gif_path = os.path.join(app.config['THUMBNAIL_FOLDER'], filename)
    
    # 如果 GIF 不存在，尝试生成
    if not os.path.exists(gif_path):
        # 找到对应的视频文件
        video_filename = filename.replace('.gif', '')
        video_path = None
        for ext in app.config['ALLOWED_EXTENSIONS']:
            test_path = os.path.join(app.config['UPLOAD_FOLDER'], video_filename)
            if os.path.exists(test_path):
                video_path = test_path
                break
            test_path = os.path.join(app.config['UPLOAD_FOLDER'], video_filename.rsplit('.', 1)[0] + '.' + ext)
            if os.path.exists(test_path):
                video_path = test_path
                break
        
        if video_path:
            generate_preview_gif(video_path, gif_path)
    
    if os.path.exists(gif_path):
        return send_from_directory(app.config['THUMBNAIL_FOLDER'], filename, mimetype='image/gif')
    else:
        # 返回占位图
        return '', 404


@app.route('/delete/<filename>', methods=['POST'])
def delete_file(filename):
    """删除视频文件"""
    try:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        thumb_name = os.path.splitext(filename)[0] + '.jpg'
        thumb_path = os.path.join(app.config['THUMBNAIL_FOLDER'], thumb_name)
        
        deleted = {'video': False, 'thumbnail': False}
        
        if os.path.exists(filepath):
            os.remove(filepath)
            deleted['video'] = True
        
        if os.path.exists(thumb_path):
            os.remove(thumb_path)
            deleted['thumbnail'] = True
        
        return jsonify({'success': True, 'deleted': deleted})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/videos')
def api_videos():
    """API - 获取视频列表"""
    videos = get_video_list()
    return jsonify({'videos': videos, 'total': len(videos)})


@app.route('/api/stats')
def api_stats():
    """API - 获取统计信息"""
    videos = get_video_list()
    total_size = sum(
        os.path.getsize(os.path.join(app.config['UPLOAD_FOLDER'], v)) 
        for v in videos if os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], v))
    )
    
    # 获取文件夹大小
    def get_folder_size(path):
        if not os.path.exists(path):
            return 0
        return sum(os.path.getsize(os.path.join(path, f)) for f in os.listdir(path) if os.path.isfile(os.path.join(path, f)))
    
    return jsonify({
        'total_videos': len(videos),
        'total_size_mb': round(total_size / 1024 / 1024, 2),
        'total_size_gb': round(total_size / 1024 / 1024 / 1024, 2),
        'uploads_size_mb': round(get_folder_size(app.config['UPLOAD_FOLDER']) / 1024 / 1024, 2),
        'thumbnails_size_mb': round(get_folder_size(app.config['THUMBNAIL_FOLDER']) / 1024 / 1024, 2)
    })


@app.route('/api/video/<filename>')
def api_video_info(filename):
    """API - 获取单个视频详细信息"""
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(filepath):
        return jsonify({'error': '文件不存在'}), 404
    
    duration = get_video_duration(filepath)
    info = get_video_info(filepath)
    play_count = get_play_count(filename)
    
    return jsonify({
        'filename': filename,
        'size_mb': get_file_size(filepath),
        'duration': format_duration(duration),
        'duration_sec': duration,
        'resolution': f"{info['width']}x{info['height']}",
        'codec': info['codec'],
        'bitrate_kbps': round(info['bitrate'] / 1000, 1) if info['bitrate'] else 0,
        'play_count': play_count
    })


# 播放次数统计文件
PLAY_COUNTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'play_counts.json')
# 视频标签/分类数据文件
VIDEO_TAGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'video_tags.json')
# 视频描述/备注数据文件
VIDEO_DESCRIPTIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'video_descriptions.json')
# 播放列表数据文件
PLAYLISTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'playlists.json')
# 观看历史文件
WATCH_HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'watch_history.json')
# 视频密码保护文件
VIDEO_PASSWORDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'video_passwords.json')
# 自定义封面文件
CUSTOM_COVERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'custom_covers.json')

def get_play_counts():
    """获取所有视频的播放次数"""
    if os.path.exists(PLAY_COUNTS_FILE):
        try:
            with open(PLAY_COUNTS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_play_count(filename, count):
    """保存播放次数"""
    counts = get_play_counts()
    counts[filename] = count
    try:
        with open(PLAY_COUNTS_FILE, 'w') as f:
            json.dump(counts, f, indent=2)
    except:
        pass

def get_play_count(filename):
    """获取单个视频的播放次数"""
    counts = get_play_counts()
    return counts.get(filename, 0)

def increment_play_count(filename):
    """增加播放次数"""
    count = get_play_count(filename) + 1
    save_play_count(filename, count)
    return count


# ===== 视频标签/分类管理 =====
def get_video_tags():
    """获取所有视频的标签数据"""
    if os.path.exists(VIDEO_TAGS_FILE):
        try:
            with open(VIDEO_TAGS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_video_tags(filename, tags):
    """保存视频标签"""
    data = get_video_tags()
    data[filename] = tags
    try:
        with open(VIDEO_TAGS_FILE, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except:
        pass

def get_video_tags_for_file(filename):
    """获取单个视频的标签"""
    data = get_video_tags()
    return data.get(filename, [])

def get_all_tags():
    """获取所有唯一的标签"""
    data = get_video_tags()
    all_tags = set()
    for tags in data.values():
        all_tags.update(tags)
    return sorted(list(all_tags))

def add_tag_to_video(filename, tag):
    """给视频添加标签"""
    tags = get_video_tags_for_file(filename)
    if tag not in tags:
        tags.append(tag)
        save_video_tags(filename, tags)
    return tags

def remove_tag_from_video(filename, tag):
    """从视频移除标签"""
    tags = get_video_tags_for_file(filename)
    if tag in tags:
        tags.remove(tag)
        save_video_tags(filename, tags)
    return tags


@app.route('/api/play/<filename>', methods=['POST'])
def api_play(filename):
    """API - 记录播放次数"""
    count = increment_play_count(filename)
    return jsonify({'success': True, 'play_count': count})


@app.route('/api/tags/<filename>', methods=['GET'])
def api_get_tags(filename):
    """API - 获取视频标签"""
    tags = get_video_tags_for_file(filename)
    return jsonify({'filename': filename, 'tags': tags})


@app.route('/api/tags/<filename>', methods=['POST'])
def api_add_tag(filename):
    """API - 添加视频标签"""
    data = request.get_json()
    tag = data.get('tag', '').strip()
    if not tag:
        return jsonify({'error': '标签不能为空'}), 400
    tags = add_tag_to_video(filename, tag)
    return jsonify({'success': True, 'tags': tags})


@app.route('/api/tags/<filename>', methods=['DELETE'])
def api_remove_tag(filename):
    """API - 删除视频标签"""
    data = request.get_json()
    tag = data.get('tag', '').strip()
    if not tag:
        return jsonify({'error': '标签不能为空'}), 400
    tags = remove_tag_from_video(filename, tag)
    return jsonify({'success': True, 'tags': tags})


@app.route('/api/tags', methods=['GET'])
def api_all_tags():
    """API - 获取所有标签"""
    tags = get_all_tags()
    # 统计每个标签的视频数量
    tag_counts = {}
    data = get_video_tags()
    for tags_list in data.values():
        for tag in tags_list:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    return jsonify({'tags': tags, 'counts': tag_counts})


# ===== 视频描述/备注管理 =====
def get_video_descriptions():
    """获取所有视频的描述数据"""
    if os.path.exists(VIDEO_DESCRIPTIONS_FILE):
        try:
            with open(VIDEO_DESCRIPTIONS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_video_description(filename, description, notes=''):
    """保存视频描述"""
    data = get_video_descriptions()
    data[filename] = {
        'description': description,
        'notes': notes,
        'updated_at': subprocess.run(['date', '+%Y-%m-%d %H:%M:%S'], capture_output=True, text=True).stdout.strip()
    }
    try:
        with open(VIDEO_DESCRIPTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存描述失败：{e}")

def get_video_description_for_file(filename):
    """获取单个视频的描述"""
    data = get_video_descriptions()
    return data.get(filename, {'description': '', 'notes': '', 'updated_at': ''})


@app.route('/api/description/<filename>', methods=['GET'])
def api_get_description(filename):
    """API - 获取视频描述"""
    desc = get_video_description_for_file(filename)
    return jsonify({
        'filename': filename,
        'description': desc.get('description', ''),
        'notes': desc.get('notes', ''),
        'updated_at': desc.get('updated_at', '')
    })


@app.route('/api/description/<filename>', methods=['POST'])
def api_save_description(filename):
    """API - 保存视频描述"""
    data = request.get_json()
    description = data.get('description', '')
    notes = data.get('notes', '')
    save_video_description(filename, description, notes)
    return jsonify({
        'success': True,
        'updated_at': subprocess.run(['date', '+%Y-%m-%d %H:%M:%S'], capture_output=True, text=True).stdout.strip()
    })


@app.route('/api/description/<filename>', methods=['DELETE'])
def api_delete_description(filename):
    """API - 删除视频描述"""
    data = get_video_descriptions()
    if filename in data:
        del data[filename]
        try:
            with open(VIDEO_DESCRIPTIONS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except:
            pass
    return jsonify({'success': True})


# ===== 播放列表/合集管理 =====
def get_playlists():
    """获取所有播放列表"""
    if os.path.exists(PLAYLISTS_FILE):
        try:
            with open(PLAYLISTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_playlists(data):
    """保存播放列表数据"""
    try:
        with open(PLAYLISTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存播放列表失败：{e}")

def create_playlist(name, description='', cover='', is_public=True):
    """创建新播放列表"""
    data = get_playlists()
    import uuid
    import datetime
    playlist_id = str(uuid.uuid4())[:8]
    data[playlist_id] = {
        'id': playlist_id,
        'name': name,
        'description': description,
        'videos': [],
        'cover': cover,  # 自定义封面
        'is_public': is_public,  # 是否公开
        'play_count': 0,
        'created_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'updated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    save_playlists(data)
    return playlist_id

def add_video_to_playlist(playlist_id, filename):
    """添加视频到播放列表"""
    data = get_playlists()
    if playlist_id in data and filename not in data[playlist_id]['videos']:
        data[playlist_id]['videos'].append(filename)
        import datetime
        data[playlist_id]['updated_at'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        save_playlists(data)
        return True
    return False

def remove_video_from_playlist(playlist_id, filename):
    """从播放列表移除视频"""
    data = get_playlists()
    if playlist_id in data and filename in data[playlist_id]['videos']:
        data[playlist_id]['videos'].remove(filename)
        import datetime
        data[playlist_id]['updated_at'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        save_playlists(data)
        return True
    return False

def delete_playlist(playlist_id):
    """删除播放列表"""
    data = get_playlists()
    if playlist_id in data:
        del data[playlist_id]
        save_playlists(data)
        return True
    return False

def reorder_playlist(playlist_id, videos):
    """重新排序播放列表"""
    data = get_playlists()
    if playlist_id in data:
        data[playlist_id]['videos'] = videos
        import datetime
        data[playlist_id]['updated_at'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        save_playlists(data)
        return True
    return False

def set_playlist_cover(playlist_id, cover):
    """设置播放列表封面"""
    data = get_playlists()
    if playlist_id in data:
        data[playlist_id]['cover'] = cover
        save_playlists(data)
        return True
    return False

def export_playlist(playlist_id):
    """导出播放列表为 JSON"""
    data = get_playlists()
    if playlist_id in data:
        return data[playlist_id]
    return None

def import_playlist(playlist_data):
    """导入播放列表"""
    data = get_playlists()
    import uuid
    import datetime
    playlist_id = str(uuid.uuid4())[:8]
    playlist_data['id'] = playlist_id
    playlist_data['created_at'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    playlist_data['updated_at'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    data[playlist_id] = playlist_data
    save_playlists(data)
    return playlist_id


@app.route('/api/playlists', methods=['GET'])
def api_get_playlists():
    """API - 获取所有播放列表"""
    data = get_playlists()
    return jsonify({'playlists': list(data.values())})


@app.route('/api/playlists', methods=['POST'])
def api_create_playlist():
    """API - 创建播放列表"""
    req_data = request.get_json()
    name = req_data.get('name', '未命名播放列表')
    description = req_data.get('description', '')
    playlist_id = create_playlist(name, description)
    return jsonify({'success': True, 'id': playlist_id})


@app.route('/api/playlists/<playlist_id>', methods=['GET'])
def api_get_playlist(playlist_id):
    """API - 获取单个播放列表"""
    data = get_playlists()
    if playlist_id in data:
        return jsonify(data[playlist_id])
    return jsonify({'error': '播放列表不存在'}), 404


@app.route('/api/playlists/<playlist_id>', methods=['POST'])
def api_add_to_playlist(playlist_id):
    """API - 添加视频到播放列表"""
    req_data = request.get_json()
    filename = req_data.get('filename')
    if not filename:
        return jsonify({'error': '缺少文件名'}), 400
    success = add_video_to_playlist(playlist_id, filename)
    return jsonify({'success': success})


@app.route('/api/playlists/<playlist_id>/<path:filename>', methods=['DELETE'])
def api_remove_from_playlist(playlist_id, filename):
    """API - 从播放列表移除视频"""
    success = remove_video_from_playlist(playlist_id, filename)
    return jsonify({'success': success})


@app.route('/api/playlists/<playlist_id>', methods=['DELETE'])
def api_delete_playlist(playlist_id):
    """API - 删除播放列表"""
    success = delete_playlist(playlist_id)
    return jsonify({'success': success})


@app.route('/api/playlists/<playlist_id>/reorder', methods=['POST'])
def api_reorder_playlist(playlist_id):
    """API - 重新排序播放列表"""
    req_data = request.get_json()
    videos = req_data.get('videos', [])
    success = reorder_playlist(playlist_id, videos)
    return jsonify({'success': success})


@app.route('/api/playlists/<playlist_id>/cover', methods=['PUT'])
def api_set_playlist_cover(playlist_id):
    """API - 设置播放列表封面"""
    req_data = request.get_json()
    cover = req_data.get('cover', '')
    success = set_playlist_cover(playlist_id, cover)
    return jsonify({'success': success})


@app.route('/api/playlists/<playlist_id>/export', methods=['GET'])
def api_export_playlist(playlist_id):
    """API - 导出播放列表"""
    data = export_playlist(playlist_id)
    if data:
        return jsonify(data)
    return jsonify({'error': '播放列表不存在'}), 404


@app.route('/api/playlists/import', methods=['POST'])
def api_import_playlist():
    """API - 导入播放列表"""
    req_data = request.get_json()
    playlist_id = import_playlist(req_data)
    return jsonify({'success': True, 'id': playlist_id})


@app.route('/api/playlists/<playlist_id>/share', methods=['GET'])
def api_share_playlist(playlist_id):
    """API - 生成播放列表分享链接"""
    import base64
    import json
    data = export_playlist(playlist_id)
    if data:
        # 编码为 base64
        share_data = base64.b64encode(json.dumps(data).encode()).decode()
        share_url = request.url_root.rstrip('/') + '/playlist/import/' + share_data
        return jsonify({
            'success': True,
            'share_url': share_url,
            'share_code': share_data[:50] + '...'
        })
    return jsonify({'error': '播放列表不存在'}), 404


@app.route('/playlist/import/<share_data>')
def import_playlist_page(share_data):
    """播放列表导入页面"""
    try:
        import base64
        playlist_data = json.loads(base64.b64decode(share_data))
        return f'''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>导入播放列表 - {playlist_data.get("name", "未知")}</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    background: linear-gradient(135deg, #1a1a2e, #16213e);
                    color: #e0e0e0;
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin: 0;
                }}
                .container {{
                    background: rgba(255,255,255,0.05);
                    padding: 40px;
                    border-radius: 20px;
                    text-align: center;
                    max-width: 500px;
                }}
                h1 {{ color: #e94560; }}
                .info {{ 
                    background: rgba(255,255,255,0.03);
                    padding: 20px;
                    border-radius: 10px;
                    margin: 20px 0;
                }}
                .btn {{
                    display: inline-block;
                    padding: 15px 40px;
                    background: linear-gradient(135deg, #e94560, #ff6b6b);
                    color: #fff;
                    text-decoration: none;
                    border-radius: 10px;
                    font-weight: 600;
                    margin: 10px;
                }}
                .btn:hover {{ transform: translateY(-2px); }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>📋 发现播放列表</h1>
                <div class="info">
                    <h2>{playlist_data.get("name", "未知播放列表")}</h2>
                    <p>{playlist_data.get("description", "无描述")}</p>
                    <p>📹 {len(playlist_data.get("videos", []))} 个视频</p>
                </div>
                <a href="/" class="btn" onclick="importPlaylist()">✅ 导入到我的列表</a>
                <a href="/" class="btn" style="background: rgba(255,255,255,0.1);">❌ 取消</a>
            </div>
            <script>
                function importPlaylist() {{
                    fetch('/api/playlists/import', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({json.dumps(playlist_data)})
                    }}).then(r => r.json()).then(data => {{
                        if(data.success) {{
                            alert('播放列表已导入！');
                            window.location.href = '/';
                        }}
                    }});
                }}
            </script>
        </body>
        </html>
        '''
    except Exception as e:
        return f'<h1>导入失败</h1><p>{str(e)}</p>', 400


# ===== 观看历史/进度记录 =====
def get_watch_history():
    """获取观看历史"""
    if os.path.exists(WATCH_HISTORY_FILE):
        try:
            with open(WATCH_HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_watch_history(data):
    """保存观看历史"""
    try:
        with open(WATCH_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except:
        pass

def update_watch_progress(filename, position, duration, device='web'):
    """更新观看进度"""
    data = get_watch_history()
    import datetime
    
    # 获取现有记录
    existing = data.get(filename, {})
    
    # 更新进度
    data[filename] = {
        'position': position,
        'duration': duration,
        'last_watched': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'progress_percent': round((position / duration * 100) if duration > 0 else 0, 1),
        'watch_count': existing.get('watch_count', 0) + 1,
        'device': device,
        'first_watched': existing.get('first_watched', datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    }
    save_watch_history(data)
    return data[filename]

def clear_watch_history():
    """清空所有观看历史"""
    save_watch_history({})
    return True

def remove_from_history(filename):
    """从历史记录中移除"""
    data = get_watch_history()
    if filename in data:
        del data[filename]
        save_watch_history(data)
        return True
    return False

def get_recent_history(limit=20):
    """获取最近的观看历史（按时间排序）"""
    data = get_watch_history()
    items = [(k, v) for k, v in data.items()]
    # 按最后观看时间排序
    items.sort(key=lambda x: x[1].get('last_watched', ''), reverse=True)
    return dict(items[:limit])

def get_watch_progress(filename):
    """获取观看进度"""
    data = get_watch_history()
    return data.get(filename, {'position': 0, 'duration': 0, 'progress_percent': 0})


@app.route('/api/history/<filename>', methods=['GET'])
def api_get_history(filename):
    """API - 获取观看进度"""
    progress = get_watch_progress(filename)
    return jsonify({'filename': filename, **progress})


@app.route('/api/history/<filename>', methods=['POST'])
def api_update_history(filename):
    """API - 更新观看进度"""
    req_data = request.get_json()
    position = req_data.get('position', 0)
    duration = req_data.get('duration', 0)
    progress = update_watch_progress(filename, position, duration)
    return jsonify({'success': True, **progress})


@app.route('/api/history', methods=['GET'])
def api_get_all_history():
    """API - 获取所有观看历史"""
    data = get_watch_history()
    return jsonify({'history': data})


@app.route('/api/history/clear', methods=['POST'])
def api_clear_history():
    """API - 清空所有观看历史"""
    success = clear_watch_history()
    return jsonify({'success': success})


@app.route('/api/history/<filename>', methods=['DELETE'])
def api_remove_history(filename):
    """API - 移除单个历史记录"""
    success = remove_from_history(filename)
    return jsonify({'success': success})


@app.route('/api/history/recent', methods=['GET'])
def api_get_recent_history():
    """API - 获取最近的观看历史"""
    limit = request.args.get('limit', 20, type=int)
    data = get_recent_history(limit)
    return jsonify({'history': data})


@app.route('/api/history/stats', methods=['GET'])
def api_get_history_stats():
    """API - 获取观看历史统计"""
    data = get_watch_history()
    
    total_videos = len(data)
    total_watch_time = sum(v.get('duration', 0) * (v.get('progress_percent', 0) / 100) for v in data.values())
    completed_videos = sum(1 for v in data.values() if v.get('progress_percent', 0) >= 95)
    
    # 按设备统计
    device_stats = {}
    for v in data.values():
        device = v.get('device', 'unknown')
        device_stats[device] = device_stats.get(device, 0) + 1
    
    return jsonify({
        'total_videos': total_videos,
        'total_watch_time_seconds': round(total_watch_time, 0),
        'total_watch_time_hours': round(total_watch_time / 3600, 2),
        'completed_videos': completed_videos,
        'in_progress_videos': total_videos - completed_videos,
        'device_stats': device_stats
    })


# ===== 视频密码保护 =====
import hashlib

def hash_password(password):
    """对密码进行 SHA256 哈希"""
    return hashlib.sha256(password.encode()).hexdigest()

def get_video_passwords():
    """获取视频密码数据"""
    if os.path.exists(VIDEO_PASSWORDS_FILE):
        try:
            with open(VIDEO_PASSWORDS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_video_passwords(data):
    """保存视频密码数据"""
    try:
        with open(VIDEO_PASSWORDS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except:
        pass

def set_video_password(filename, password, hint='', access_log=None):
    """设置视频密码"""
    data = get_video_passwords()
    if password:
        data[filename] = {
            'password': hash_password(password),  # 存储哈希值
            'hint': hint,  # 密码提示
            'access_log': access_log or [],  # 访问日志
            'created_at': subprocess.run(['date', '+%Y-%m-%d %H:%M:%S'], capture_output=True, text=True).stdout.strip(),
            'access_count': 0
        }
    elif filename in data:
        del data[filename]
    save_video_passwords(data)
    return True

def verify_video_password(filename, password):
    """验证视频密码"""
    data = get_video_passwords()
    if filename not in data:
        return True  # 没有密码的视频直接通过
    
    hashed_input = hash_password(password)
    stored_hash = data[filename].get('password', '')
    
    # 记录访问尝试
    log_access(filename, password == '', success=(hashed_input == stored_hash))
    
    return hashed_input == stored_hash

def is_video_protected(filename):
    """检查视频是否有密码保护"""
    data = get_video_passwords()
    return filename in data

def get_password_hint(filename):
    """获取密码提示"""
    data = get_video_passwords()
    if filename in data:
        return data[filename].get('hint', '')
    return ''

def log_access(filename, success, ip='unknown'):
    """记录访问日志"""
    data = get_video_passwords()
    if filename in data:
        import datetime
        log_entry = {
            'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'success': success,
            'ip': ip
        }
        if 'access_log' not in data[filename]:
            data[filename]['access_log'] = []
        data[filename]['access_log'].append(log_entry)
        
        # 成功访问增加计数
        if success:
            data[filename]['access_count'] = data[filename].get('access_count', 0) + 1
        
        # 只保留最近 100 条记录
        data[filename]['access_log'] = data[filename]['access_log'][-100:]
        
        save_video_passwords(data)

def get_access_log(filename):
    """获取访问日志"""
    data = get_video_passwords()
    if filename in data:
        return data[filename].get('access_log', [])
    return []

def get_protected_videos():
    """获取所有受保护的视频列表"""
    data = get_video_passwords()
    return list(data.keys())

def batch_set_password(filenames, password, hint=''):
    """批量设置密码"""
    for filename in filenames:
        set_video_password(filename, password, hint)
    return True

def batch_remove_password(filenames):
    """批量移除密码"""
    for filename in filenames:
        set_video_password(filename, '')
    return True


@app.route('/api/password/<filename>', methods=['GET'])
def api_check_password(filename):
    """API - 检查视频是否有密码"""
    return jsonify({
        'filename': filename,
        'protected': is_video_protected(filename),
        'hint': get_password_hint(filename)
    })


@app.route('/api/password/<filename>', methods=['POST'])
def api_verify_password(filename):
    """API - 验证密码"""
    req_data = request.get_json()
    password = req_data.get('password', '')
    ip = request.remote_addr
    
    if verify_video_password(filename, password):
        log_access(filename, True, ip)
        return jsonify({'success': True})
    
    log_access(filename, False, ip)
    return jsonify({'success': False, 'error': '密码错误'}), 401


@app.route('/api/password/<filename>', methods=['PUT'])
def api_set_password(filename):
    """API - 设置/移除密码"""
    req_data = request.get_json()
    password = req_data.get('password', '')
    hint = req_data.get('hint', '')
    
    if password and len(password) < 4:
        return jsonify({'error': '密码至少 4 位'}), 400
    
    set_video_password(filename, password, hint)
    return jsonify({'success': True, 'protected': bool(password)})


@app.route('/api/password/<filename>/hint', methods=['GET'])
def api_get_hint(filename):
    """API - 获取密码提示"""
    hint = get_password_hint(filename)
    return jsonify({
        'filename': filename,
        'hint': hint,
        'has_hint': bool(hint)
    })


@app.route('/api/password/<filename>/log', methods=['GET'])
def api_get_access_log(filename):
    """API - 获取访问日志"""
    log = get_access_log(filename)
    return jsonify({
        'filename': filename,
        'log': log,
        'total': len(log)
    })


@app.route('/api/password/batch', methods=['POST'])
def api_batch_set_password():
    """API - 批量设置密码"""
    req_data = request.get_json()
    filenames = req_data.get('filenames', [])
    password = req_data.get('password', '')
    hint = req_data.get('hint', '')
    
    if not filenames:
        return jsonify({'error': '没有指定文件'}), 400
    
    if password and len(password) < 4:
        return jsonify({'error': '密码至少 4 位'}), 400
    
    batch_set_password(filenames, password, hint)
    return jsonify({'success': True, 'count': len(filenames)})


@app.route('/api/password/batch/remove', methods=['POST'])
def api_batch_remove_password():
    """API - 批量移除密码"""
    req_data = request.get_json()
    filenames = req_data.get('filenames', [])
    
    if not filenames:
        return jsonify({'error': '没有指定文件'}), 400
    
    batch_remove_password(filenames)
    return jsonify({'success': True, 'count': len(filenames)})


@app.route('/api/password/protected', methods=['GET'])
def api_get_protected_videos():
    """API - 获取所有受保护的视频"""
    protected = get_protected_videos()
    data = get_video_passwords()
    
    result = []
    for filename in protected:
        video_data = data.get(filename, {})
        result.append({
            'filename': filename,
            'created_at': video_data.get('created_at', ''),
            'access_count': video_data.get('access_count', 0),
            'has_hint': bool(video_data.get('hint', ''))
        })
    
    return jsonify({
        'protected': result,
        'total': len(result)
    })


@app.route('/api/password/<filename>/stats', methods=['GET'])
def api_get_password_stats(filename):
    """API - 获取密码统计"""
    data = get_video_passwords()
    if filename not in data:
        return jsonify({'error': '视频没有密码保护'}), 404
    
    video_data = data[filename]
    log = video_data.get('access_log', [])
    
    success_count = sum(1 for entry in log if entry.get('success', False))
    fail_count = len(log) - success_count
    
    return jsonify({
        'filename': filename,
        'protected': True,
        'access_count': video_data.get('access_count', 0),
        'total_attempts': len(log),
        'success_count': success_count,
        'fail_count': fail_count,
        'created_at': video_data.get('created_at', ''),
        'has_hint': bool(video_data.get('hint', ''))
    })


# ===== 自定义封面 =====
def get_custom_covers():
    """获取自定义封面数据"""
    if os.path.exists(CUSTOM_COVERS_FILE):
        try:
            with open(CUSTOM_COVERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_custom_covers(data):
    """保存自定义封面数据"""
    try:
        with open(CUSTOM_COVERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except:
        pass

def set_custom_cover(filename, cover_filename):
    """设置自定义封面"""
    data = get_custom_covers()
    if cover_filename:
        data[filename] = {'cover': cover_filename}
    elif filename in data:
        del data[filename]
    save_custom_covers(data)
    return True

def get_custom_cover(filename):
    """获取自定义封面"""
    data = get_custom_covers()
    return data.get(filename, {}).get('cover', '')


@app.route('/api/cover/<filename>', methods=['GET'])
def api_get_cover(filename):
    """API - 获取视频封面"""
    cover = get_custom_cover(filename)
    return jsonify({
        'filename': filename,
        'custom_cover': cover,
        'has_custom': bool(cover)
    })


@app.route('/api/cover/<filename>', methods=['PUT'])
def api_set_cover(filename):
    """API - 设置自定义封面"""
    req_data = request.get_json()
    cover_filename = req_data.get('cover', '')
    set_custom_cover(filename, cover_filename)
    return jsonify({'success': True, 'cover': cover_filename})


@app.route('/api/cover/<filename>', methods=['DELETE'])
def api_delete_cover(filename):
    """API - 删除自定义封面"""
    set_custom_cover(filename, '')
    return jsonify({'success': True})


@app.route('/covers/<filename>')
def serve_custom_cover(filename):
    """自定义封面服务"""
    return send_from_directory(app.config['THUMBNAIL_FOLDER'], filename, mimetype='image/jpeg')


@app.route('/api/cover/upload/<video_filename>', methods=['POST'])
def api_upload_cover(video_filename):
    """API - 上传视频封面"""
    if 'cover' not in request.files:
        return jsonify({'error': '没有文件'}), 400
    
    file = request.files['cover']
    if file.filename == '':
        return jsonify({'error': '文件名为空'}), 400
    
    # 验证文件类型
    allowed_extensions = {'jpg', 'jpeg', 'png', 'webp'}
    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    if ext not in allowed_extensions:
        return jsonify({'error': '不支持的文件格式'}), 400
    
    try:
        # 生成封面文件名
        cover_filename = f"{video_filename.rsplit('.', 1)[0]}_cover.{ext}"
        cover_path = os.path.join(app.config['THUMBNAIL_FOLDER'], cover_filename)
        
        # 保存文件
        file.save(cover_path)
        
        # 验证文件大小
        if os.path.getsize(cover_path) > 5 * 1024 * 1024:  # 5MB 限制
            os.remove(cover_path)
            return jsonify({'error': '文件过大（最大 5MB）'}), 400
        
        # 更新封面记录
        set_custom_cover(video_filename, cover_filename)
        
        return jsonify({
            'success': True,
            'cover': cover_filename,
            'url': f'/covers/{cover_filename}'
        })
    except Exception as e:
        return jsonify({'error': f'上传失败：{str(e)}'}), 500


@app.route('/api/cover/select/<video_filename>', methods=['GET'])
def api_get_cover_options(video_filename):
    """API - 获取可选封面列表"""
    # 获取视频所在目录
    video_path = os.path.join(app.config['UPLOAD_FOLDER'], video_filename)
    if not os.path.exists(video_path):
        return jsonify({'error': '视频不存在'}), 404
    
    # 获取视频关键帧作为封面选项
    options = []
    
    # 自动生成 3 个时间点的缩略图作为选项
    duration = get_video_duration(video_path)
    if duration > 0:
        time_points = [
            max(1, duration * 0.1),    # 10% 位置
            max(1, duration * 0.3),    # 30% 位置
            max(1, duration * 0.5),    # 50% 位置
        ]
        
        for i, time_pos in enumerate(time_points):
            thumb_filename = f"{video_filename.rsplit('.', 1)[0]}_option_{i}.jpg"
            thumb_path = os.path.join(app.config['THUMBNAIL_FOLDER'], thumb_filename)
            
            try:
                cmd = [
                    'ffmpeg',
                    '-i', video_path,
                    '-ss', str(time_pos),
                    '-vframes', '1',
                    '-vf', 'scale=320:-1',
                    '-y',
                    thumb_path
                ]
                result = subprocess.run(cmd, capture_output=True, timeout=30)
                if result.returncode == 0 and os.path.exists(thumb_path):
                    options.append({
                        'filename': thumb_filename,
                        'time': round(time_pos, 1),
                        'url': f'/thumbnails/{thumb_filename}'
                    })
            except:
                pass
    
    # 添加当前自定义封面（如果有）
    current_cover = get_custom_cover(video_filename)
    if current_cover:
        options.insert(0, {
            'filename': current_cover,
            'time': 0,
            'url': f'/covers/{current_cover}',
            'is_current': True
        })
    
    return jsonify({
        'video': video_filename,
        'options': options,
        'current': current_cover
    })


@app.route('/api/cover/apply/<video_filename>', methods=['POST'])
def api_apply_cover(video_filename):
    """API - 应用选定的封面"""
    req_data = request.get_json()
    cover_filename = req_data.get('cover', '')
    
    if not cover_filename:
        return jsonify({'error': '封面文件名为空'}), 400
    
    # 验证封面文件存在
    cover_path = os.path.join(app.config['THUMBNAIL_FOLDER'], cover_filename)
    if not os.path.exists(cover_path):
        return jsonify({'error': '封面文件不存在'}), 404
    
    # 应用封面
    set_custom_cover(video_filename, cover_filename)
    
    return jsonify({
        'success': True,
        'cover': cover_filename
    })


@app.route('/api/covers/gallery', methods=['GET'])
def api_cover_gallery():
    """API - 获取封面图库"""
    # 获取所有自定义封面
    covers_data = get_custom_covers()
    gallery = []
    
    for video_filename, cover_data in covers_data.items():
        cover_filename = cover_data.get('cover', '')
        cover_path = os.path.join(app.config['THUMBNAIL_FOLDER'], cover_filename)
        if os.path.exists(cover_path):
            gallery.append({
                'video': video_filename,
                'cover': cover_filename,
                'url': f'/covers/{cover_filename}',
                'size': os.path.getsize(cover_path)
            })
    
    return jsonify({'gallery': gallery, 'total': len(gallery)})


# ===== PWA 和移动端支持 =====
@app.route('/offline.html')
def offline_page():
    """离线页面"""
    return render_template('offline.html')


@app.route('/static/sw.js')
def service_worker():
    """Service Worker"""
    return send_from_directory('static', 'sw.js', mimetype='application/javascript')


@app.route('/static/manifest.json')
def manifest():
    """PWA Manifest"""
    return send_from_directory('static', 'manifest.json', mimetype='application/json')


if __name__ == '__main__':
    # 创建必要目录
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['ORIGINAL_FOLDER'], exist_ok=True)
    os.makedirs(app.config['THUMBNAIL_FOLDER'], exist_ok=True)
    
    print(f"🎬 视频服务器启动中...")
    print(f"📁 上传目录：{app.config['UPLOAD_FOLDER']}")
    print(f"🗜️  自动压缩：{'开启' if app.config['COMPRESS_VIDEO'] else '关闭'}")
    print(f"📊 压缩质量：CRF={app.config['CRF_VALUE']}, 最大宽度={app.config['MAX_WIDTH']}px")
    print(f"🌐 访问地址：http://localhost:{app.config['PORT']}")
    print(f"📱 局域网访问：http://<你的 IP>:{app.config['PORT']}")
    print("")
    
    app.run(host=app.config['HOST'], port=app.config['PORT'], debug=app.config['DEBUG'])
