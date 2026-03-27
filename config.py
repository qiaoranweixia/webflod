"""
项目配置文件
"""
import os

class Config:
    # 基础配置
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-change-in-production'
    
    # 上传配置
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    ORIGINAL_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'originals')
    THUMBNAIL_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'thumbnails')
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024 * 1024  # 2GB 最大上传限制
    
    # 允许的视频格式
    ALLOWED_EXTENSIONS = {'mp4', 'webm', 'ogg', 'mov', 'avi', 'mkv', 'flv', 'wmv'}
    
    # 允许的音频格式
    ALLOWED_AUDIO_EXTENSIONS = {'mp3', 'wav', 'm4a', 'aac', 'flac', 'ogg', 'wma'}
    
    # 压缩配置
    COMPRESS_VIDEO = True  # 是否自动压缩视频
    COMPRESSION_PRESET = 'medium'  # ultrafast, superfast, fast, medium, slow, slower, veryslow
    CRF_VALUE = 28  # 压缩质量 (0-51, 越大压缩越高，推荐 23-28)
    MAX_WIDTH = 1280  # 最大宽度（保持比例缩放）
    AUDIO_BITRATE = '128k'  # 视频中的音频比特率
    
    # 音频压缩配置
    COMPRESS_AUDIO = True  # 是否自动压缩音频
    AUDIO_COMPRESSION_BITRATE = '192k'  # 音频输出比特率
    
    # 缩略图配置
    GENERATE_THUMBNAIL = True
    THUMBNAIL_TIME = 5  # 在第几秒截取缩略图
    
    # 分页配置
    VIDEOS_PER_PAGE = 12
    
    # 服务器配置
    HOST = '0.0.0.0'
    PORT = 5001
    DEBUG = False
