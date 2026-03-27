/**
 * 视频中心 - 前端交互脚本 (增强版)
 */

let currentIndex = 0;
let autoplay = true;
let audioMode = false;
let isMinimized = false;
let isPlaying = false;
let favorites = JSON.parse(localStorage.getItem('videoFavorites') || '[]');
let currentSort = 'date';
let selectedForDelete = [];
let currentTagFilter = 'all';
let currentTagVideo = null;
let currentTagIndex = null;
let allTags = [];
let tagCounts = {};
let previewTimers = {};
let currentDescVideo = null;
let currentDescTab = 'edit';
let currentSettingsVideo = null;
let currentSettingsIndex = null;

// ===== 初始化 =====

// 图片懒加载
function initLazyLoading() {
    if ('IntersectionObserver' in window) {
        const lazyImages = document.querySelectorAll('img[loading="lazy"]');
        
        const imageObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    if (img.dataset.src) {
                        img.src = img.dataset.src;
                        img.removeAttribute('loading');
                        imageObserver.unobserve(img);
                    }
                }
            });
        });
        
        lazyImages.forEach(img => imageObserver.observe(img));
    }
}

// DOMContentLoaded 事件监听器
document.addEventListener('DOMContentLoaded', function() {
    // 图片懒加载
    initLazyLoading();
    
    // 文件选择显示
    const fileInput = document.getElementById('file');
    const fileInfo = document.getElementById('fileInfo');
    
    if (fileInput) {
        fileInput.addEventListener('change', function(e) {
            const files = e.target.files;
            if (files.length > 0) {
                const totalSize = Array.from(files).reduce((sum, f) => sum + f.size, 0);
                const sizeStr = totalSize > 1024 * 1024 * 1024 
                    ? `${(totalSize / 1024 / 1024 / 1024).toFixed(2)} GB`
                    : `${(totalSize / 1024 / 1024).toFixed(2)} MB`;
                
                fileInfo.innerHTML = `
                    <strong>📄 已选择 ${files.length} 个文件</strong><br>
                    <span>${files.map(f => f.name).join(', ').substring(0, 100)}${files.length > 1 ? '...' : ''}</span><br>
                    <span style="color: #3b82f6;">💾 总大小：${sizeStr}</span>
                `;
                
                // 显示缩略图预览（第一个文件）
                if (files[0] && files[0].type.startsWith('video/')) {
                    const video = document.createElement('video');
                    video.src = URL.createObjectURL(files[0]);
                    video.addEventListener('loadedmetadata', function() {
                        const duration = Math.floor(video.duration);
                        const mins = Math.floor(duration / 60);
                        const secs = duration % 60;
                        fileInfo.innerHTML += `<br><span style="color: #8b5cf6;">⏱️ 时长：${mins}:${secs.toString().padStart(2, '0')}</span>`;
                    });
                }
            }
        });
    }
    
    // 表单提交
    const uploadForm = document.getElementById('uploadForm');
    if (uploadForm) {
        uploadForm.addEventListener('submit', handleUpload);
    }
    
    // 搜索框回车
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') filterVideos();
        });
    }
    
    // 加载收藏状态
    updateFavoriteButtons();
    
    // 加载主题
    loadTheme();
});

// ===== 主题切换 =====
function toggleTheme() {
    const body = document.body;
    const isDark = !body.classList.contains('light-theme');
    
    if (isDark) {
        body.classList.add('light-theme');
        localStorage.setItem('theme', 'light');
        showToast('☀️ 已切换到浅色主题', 'info');
    } else {
        body.classList.remove('light-theme');
        localStorage.setItem('theme', 'dark');
        showToast('🌙 已切换到深色主题', 'info');
    }
}

function loadTheme() {
    const theme = localStorage.getItem('theme') || 'dark';
    if (theme === 'light') {
        document.body.classList.add('light-theme');
    }
}

// ===== 上传处理 =====
let uploadStartTime = 0;
let selectedFiles = []; // 存储选中的文件

// 文件列表管理
function updateFileList(files) {
    const preview = document.getElementById('fileListPreview');
    const fileList = document.getElementById('fileList');
    const fileCount = document.getElementById('fileCount');
    const fileListSummary = document.getElementById('fileListSummary');
    
    if (!files || files.length === 0) {
        if (preview) preview.style.display = 'none';
        return;
    }
    
    // 显示预览区域
    if (preview) preview.style.display = 'block';
    if (fileCount) fileCount.textContent = files.length;
    
    // 计算总大小和总时长
    let totalSize = 0;
    let totalDuration = 0;
    let videoCount = 0;
    
    files.forEach(file => {
        totalSize += file.size;
        if (file.duration) {
            totalDuration += file.duration;
            videoCount++;
        }
    });
    
    // 更新摘要
    const sizeStr = totalSize > 1024 * 1024 * 1024 
        ? `${(totalSize / 1024 / 1024 / 1024).toFixed(2)} GB`
        : `${(totalSize / 1024 / 1024).toFixed(2)} MB`;
    
    const durationStr = videoCount > 0 
        ? `总时长：${formatDuration(totalDuration)}`
        : '时长计算中...';
    
    if (fileListSummary) {
        fileListSummary.innerHTML = `
            <strong>💾 总大小：${sizeStr}</strong> | 
            <strong>📹 视频：${videoCount}/${files.length}</strong> | 
            <strong>${durationStr}</strong>
        `;
    }
    
    // 更新文件列表
    if (fileList) {
        fileList.innerHTML = '';
        Array.from(files).forEach((file, index) => {
            const li = document.createElement('li');
            li.className = 'file-list-item';
            
            const sizeStr = file.size > 1024 * 1024 
                ? `${(file.size / 1024 / 1024).toFixed(2)} MB`
                : `${(file.size / 1024).toFixed(2)} KB`;
            
            const durationStr = file.duration ? formatDuration(file.duration) : '--:--';
            
            li.innerHTML = `
                <span class="file-item-icon">🎬</span>
                <div class="file-item-info">
                    <div class="file-item-name" title="${file.name}">${file.name}</div>
                    <div class="file-item-meta">
                        <span class="file-item-size">💾 ${sizeStr}</span>
                        <span class="file-item-duration">⏱️ ${durationStr}</span>
                    </div>
                </div>
                <button type="button" class="file-item-remove" onclick="removeFile(${index})" title="移除文件">
                    ×
                </button>
            `;
            
            fileList.appendChild(li);
        });
    }
}

// 移除单个文件
function removeFile(index) {
    if (index >= 0 && index < selectedFiles.length) {
        selectedFiles.splice(index, 1);
        
        // 更新文件输入
        const fileInput = document.getElementById('file');
        const dataTransfer = new DataTransfer();
        selectedFiles.forEach(file => dataTransfer.items.add(file));
        fileInput.files = dataTransfer.files;
        
        // 更新列表显示
        updateFileList(selectedFiles);
        
        // 如果全部移除，隐藏预览
        if (selectedFiles.length === 0) {
            document.getElementById('fileListPreview').style.display = 'none';
        }
        
        showToast(`已移除 1 个文件`, 'info');
    }
}

// 清空所有文件
function clearAllFiles() {
    selectedFiles = [];
    const fileInput = document.getElementById('file');
    fileInput.value = '';
    document.getElementById('fileListPreview').style.display = 'none';
    document.getElementById('fileInfo').innerHTML = '';
    showToast('已清空所有文件', 'info');
}

// 格式化时长
function formatDuration(seconds) {
    if (!seconds || isNaN(seconds)) return '--:--';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function handleUpload(e) {
    e.preventDefault();
    
    const form = e.target;
    const fileInput = document.getElementById('file');
    const files = fileInput.files;
    const compress = document.getElementById('compressCheck').checked;
    
    if (!files || files.length === 0) {
        showToast('请选择至少一个视频文件', 'error');
        return;
    }
    
    const formData = new FormData(form);
    formData.append('compress', compress ? 'true' : 'false');
    
    const progressContainer = document.getElementById('progressContainer');
    const progressBar = document.getElementById('progressBar');
    const progressLabel = document.getElementById('progressLabel');
    const progressPercent = document.getElementById('progressPercent');
    const compressionResult = document.getElementById('compressionResult');
    const uploadBtn = document.getElementById('uploadBtn');
    
    // 显示进度
    if (progressContainer) {
        progressContainer.style.display = 'block';
        progressBar.innerHTML = '<div class="progress-bar-fill" id="progressBarFill" style="width: 0%"></div>';
        progressLabel.textContent = '准备上传...';
        progressPercent.textContent = '0%';
        compressionResult.innerHTML = '';
    }
    
    // 禁用按钮
    if (uploadBtn) {
        uploadBtn.disabled = true;
        uploadBtn.innerHTML = '<span class="spinner"></span> 上传中...';
    }
    
    // 记录开始时间
    uploadStartTime = new Date().getTime();
    
    const xhr = new XMLHttpRequest();
    let retryCount = 0;
    const maxRetries = 3;
    
    // 重试函数
    function retryUpload() {
        if (retryCount < maxRetries) {
            retryCount++;
            const delay = Math.min(1000 * Math.pow(2, retryCount), 10000); // 指数退避
            
            showToast(`网络不稳定，${delay/1000}秒后重试... (${retryCount}/${maxRetries})`, 'warning');
            
            setTimeout(() => {
                uploadStartTime = new Date().getTime(); // 重置时间
                xhr.send(formData);
            }, delay);
        } else {
            showToast('上传失败，请检查网络连接后重试', 'error');
            if (uploadBtn) {
                uploadBtn.disabled = false;
                uploadBtn.innerHTML = '<span class="btn-text">⬆️ 重新上传</span>';
            }
        }
    }
    
    // 进度监听（增强版：显示速度和剩余时间）
    xhr.upload.addEventListener('progress', function(e) {
        if (e.lengthComputable) {
            const percent = Math.round((e.loaded / e.total) * 100);
            const fill = document.getElementById('progressBarFill');
            if (fill) fill.style.width = percent + '%';
            
            // 计算上传速度和剩余时间
            const currentTime = new Date().getTime();
            const timeElapsed = (currentTime - uploadStartTime) / 1000; // 秒
            const loadedMB = (e.loaded / (1024 * 1024)).toFixed(2);
            const totalMB = (e.total / (1024 * 1024)).toFixed(2);
            
            if (timeElapsed > 0) {
                const speedMBps = (e.loaded / timeElapsed / (1024 * 1024)).toFixed(2);
                const remainingBytes = e.total - e.loaded;
                const remainingSeconds = Math.ceil(remainingBytes / (e.loaded / timeElapsed));
                
                // 更新进度标签
                if (progressLabel) {
                    progressLabel.innerHTML = `已上传 ${loadedMB}/${totalMB} MB | ${speedMBps} MB/s`;
                }
                if (progressPercent) {
                    progressPercent.textContent = `${percent}% | 剩余 ${remainingSeconds}秒`;
                }
            }
            if (progressPercent) progressPercent.textContent = percent + '%';
            if (progressLabel) progressLabel.textContent = `正在上传 (${Math.round(e.loaded / 1024 / 1024)} MB / ${Math.round(e.total / 1024 / 1024)} MB)`;
        }
    });
    
    // 完成处理
    xhr.addEventListener('load', function() {
        if (uploadBtn) {
            uploadBtn.disabled = false;
            uploadBtn.innerHTML = '<span class="btn-text">⬆️ 开始上传</span>';
        }
        
        if (xhr.status === 200) {
            try {
                const data = JSON.parse(xhr.responseText);
                if (data.success) {
                    // 显示压缩结果
                    if (data.compression && data.compression.length > 0) {
                        let resultHtml = '<strong>🗜️ 压缩结果：</strong><br>';
                        data.compression.forEach(item => {
                            if (item.saved) {
                                resultHtml += `✅ ${item.filename}: ${item.original} MB → ${item.compressed} MB (节省 ${item.saved}%)<br>`;
                            } else if (item.skipped) {
                                resultHtml += `⚠️ ${item.filename}: ${item.reason}<br>`;
                            }
                        });
                        if (compressionResult) compressionResult.innerHTML = resultHtml;
                    }
                    
                    showToast(`上传成功！${data.uploaded.length} 个文件`, 'success');
                    if (progressLabel) progressLabel.textContent = '上传完成！';
                    setTimeout(() => location.reload(), 2000);
                } else {
                    showToast(data.error || '上传失败', 'error');
                }
            } catch (err) {
                showToast('上传成功，刷新页面查看', 'success');
                setTimeout(() => location.reload(), 1500);
            }
        } else {
            showToast('上传失败：HTTP ' + xhr.status, 'error');
        }
    });
    
    // 错误处理（增强版：支持重试）
    xhr.addEventListener('error', function() {
        if (uploadBtn) {
            uploadBtn.disabled = false;
            uploadBtn.innerHTML = '<span class="btn-text">⬆️ 重新上传</span>';
        }
        
        // 显示错误详情和重试按钮
        const errorDetails = '网络错误，可能是服务器断开或网络不稳定';
        showToast(errorDetails, 'error');
        
        // 触发重试
        retryUpload();
    });
    
    // 超时处理
    xhr.addEventListener('timeout', function() {
        if (uploadBtn) {
            uploadBtn.disabled = false;
            uploadBtn.innerHTML = '<span class="btn-text">⬆️ 重新上传</span>';
        }
        showToast('上传超时，请重试', 'error');
        retryUpload();
    });
    
    // 设置超时时间（5 分钟）
    xhr.timeout = 300000;
    
    xhr.open('POST', '/upload');
    xhr.send(formData);
}

// ===== 搜索功能 =====
function filterVideos() {
    const query = document.getElementById('searchInput').value.toLowerCase();
    document.querySelectorAll('.video-card').forEach(card => {
        const name = card.dataset.name.toLowerCase();
        card.style.display = name.includes(query) ? 'block' : 'none';
    });
}

function clearSearch() {
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.value = '';
        searchInput.focus();
    }
    document.querySelectorAll('.video-card').forEach(card => {
        card.style.display = 'block';
    });
}

function refreshPage() {
    location.reload();
}

// ===== 分页跳转 =====
function jumpToPage() {
    const pageInput = document.getElementById('pageInput');
    if (!pageInput) return;
    
    const page = pageInput.value;
    const maxPage = window.totalPages || 1;
    if (page >= 1 && page <= maxPage) {
        window.location.href = '?page=' + page;
    } else {
        showToast('请输入有效页码 (1-' + maxPage + ')', 'error');
    }
}

// ===== 排序功能 =====
function sortVideos(sortBy) {
    currentSort = sortBy;
    const url = new URL(window.location);
    url.searchParams.set('sort', sortBy);
    window.location.href = url.toString();
}

// ===== 收藏功能 =====
function toggleFavorite(filename) {
    const index = favorites.indexOf(filename);
    if (index > -1) {
        favorites.splice(index, 1);
        showToast('⭐ 已取消收藏', 'info');
    } else {
        favorites.push(filename);
        showToast('⭐ 已添加到收藏', 'success');
    }
    localStorage.setItem('videoFavorites', JSON.stringify(favorites));
    updateFavoriteButtons();
}

function updateFavoriteButtons() {
    document.querySelectorAll('.btn-favorite').forEach(btn => {
        const filename = btn.dataset.filename;
        if (favorites.includes(filename)) {
            btn.innerHTML = '⭐ 已收藏';
            btn.classList.add('active');
        } else {
            btn.innerHTML = '☆ 收藏';
            btn.classList.remove('active');
        }
    });
}

function showFavoritesOnly() {
    document.querySelectorAll('.video-card').forEach(card => {
        const name = card.dataset.name;
        card.style.display = favorites.includes(name) ? 'block' : 'none';
    });
}

// ===== 批量选择 =====
function toggleSelect(filename) {
    const index = selectedForDelete.indexOf(filename);
    if (index > -1) {
        selectedForDelete.splice(index, 1);
    } else {
        selectedForDelete.push(filename);
    }
    updateBatchButtons();
}

function updateBatchButtons() {
    const batchBar = document.getElementById('batchBar');
    const batchCount = document.getElementById('batchCount');
    const batchDelete = document.getElementById('batchDelete');
    const batchCancel = document.getElementById('batchCancel');
    
    if (selectedForDelete.length > 0) {
        if (batchBar) batchBar.style.display = 'flex';
        if (batchCount) batchCount.textContent = selectedForDelete.length;
    } else {
        if (batchBar) batchBar.style.display = 'none';
    }
}

function batchDelete() {
    if (selectedForDelete.length === 0) return;
    
    if (confirm(`确定要删除选中的 ${selectedForDelete.length} 个视频吗？\n此操作不可恢复！`)) {
        let deleted = 0;
        const total = selectedForDelete.length;
        
        Promise.all(selectedForDelete.map(filename => 
            fetch('/delete/' + encodeURIComponent(filename), { method: 'POST' })
                .then(r => r.json())
                .then(data => { if (data.success) deleted++; })
                .catch(() => {})
        )).then(() => {
            showToast(`删除完成：${deleted}/${total}`, deleted === total ? 'success' : 'warning');
            setTimeout(() => location.reload(), 1000);
        });
    }
}

function cancelBatch() {
    selectedForDelete = [];
    updateBatchButtons();
    document.querySelectorAll('.video-checkbox').forEach(cb => {
        cb.checked = false;
    });
}

function toggleAllSelect() {
    const allCheckbox = document.getElementById('selectAll');
    const checkboxes = document.querySelectorAll('.video-checkbox');
    
    checkboxes.forEach(cb => {
        cb.checked = allCheckbox.checked;
        const filename = cb.dataset.filename;
        if (allCheckbox.checked) {
            if (!selectedForDelete.includes(filename)) selectedForDelete.push(filename);
        } else {
            const index = selectedForDelete.indexOf(filename);
            if (index > -1) selectedForDelete.splice(index, 1);
        }
    });
    updateBatchButtons();
}

// ===== 删除视频 =====
function deleteVideo(filename) {
    if (confirm('确定要删除 "' + filename + '" 吗？\n此操作不可恢复！')) {
        showToast('正在删除...', 'info');
        
        fetch('/delete/' + encodeURIComponent(filename), { method: 'POST' })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    showToast('删除成功', 'success');
                    setTimeout(() => location.reload(), 800);
                } else {
                    showToast(data.error || '删除失败', 'error');
                }
            })
            .catch(err => {
                showToast('网络错误', 'error');
            });
    }
}

// ===== 下载视频 =====
function downloadVideo(filename) {
    const a = document.createElement('a');
    a.href = '/videos/' + encodeURIComponent(filename);
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    showToast('📥 开始下载', 'success');
}

// ===== 视频信息 =====
function showVideoInfo(filename) {
    const modal = document.getElementById('infoModal');
    const body = document.getElementById('infoModalBody');
    
    if (!modal || !body) return;
    
    body.innerHTML = '<div class="loading"><span class="spinner"></span> 加载中...</div>';
    modal.style.display = 'block';
    
    // 并行获取视频信息和描述
    Promise.all([
        fetch('/api/video/' + encodeURIComponent(filename)).then(r => r.json()),
        fetch('/api/description/' + encodeURIComponent(filename)).then(r => r.json())
    ])
    .then(([videoData, descData]) => {
        if (videoData.error) {
            body.innerHTML = `<p style="color: #ef4444;">${videoData.error}</p>`;
            return;
        }
        
        // 生成描述预览（截取前 200 字符）
        let descPreview = '';
        if (descData.description && descData.description.trim().length > 0) {
            const plainText = descData.description.replace(/[#*`>\[\]]/g, '').trim();
            const preview = plainText.substring(0, 200) + (plainText.length > 200 ? '...' : '');
            descPreview = `
                <div class="info-item" style="display: block;">
                    <span class="info-label" style="display: block; margin-bottom: 8px;">📝 描述预览</span>
                    <p style="color: #888; font-size: 13px; line-height: 1.6;">${preview}</p>
                    <button class="btn-description" onclick="closeInfoModal(); showDescription('${filename}')" 
                            style="margin-top: 10px; padding: 6px 12px; font-size: 12px;">查看全部</button>
                </div>
            `;
        }
        
        body.innerHTML = `
            <div class="info-item">
                <span class="info-label">文件名</span>
                <span class="info-value" style="word-break: break-all;">${videoData.filename}</span>
            </div>
            <div class="info-item">
                <span class="info-label">文件大小</span>
                <span class="info-value">${videoData.size_mb} MB</span>
            </div>
            <div class="info-item">
                <span class="info-label">视频时长</span>
                <span class="info-value">${videoData.duration}</span>
            </div>
            <div class="info-item">
                <span class="info-label">分辨率</span>
                <span class="info-value">${videoData.resolution}</span>
            </div>
            <div class="info-item">
                <span class="info-label">视频编码</span>
                <span class="info-value">${videoData.codec}</span>
            </div>
            <div class="info-item">
                <span class="info-label">视频码率</span>
                <span class="info-value">${videoData.bitrate_kbps} kbps</span>
            </div>
            ${videoData.play_count ? `
            <div class="info-item">
                <span class="info-label">播放次数</span>
                <span class="info-value">${videoData.play_count} 次</span>
            </div>
            ` : ''}
            ${descPreview}
            <div class="info-actions" style="margin-top: 20px; display: flex; gap: 10px;">
                <button class="btn-play" onclick="downloadVideo('${filename}')" style="flex: 1;">📥 下载</button>
                <button class="btn-info" onclick="closeInfoModal()" style="flex: 1;">关闭</button>
            </div>
        `;
    })
    .catch(err => {
        body.innerHTML = `<p style="color: #ef4444;">加载失败</p>`;
    });
}

function closeInfoModal() {
    const modal = document.getElementById('infoModal');
    if (modal) modal.style.display = 'none';
}

// 点击模态框外部关闭
const infoModal = document.getElementById('infoModal');
if (infoModal) {
    infoModal.addEventListener('click', function(e) {
        if (e.target === this) closeInfoModal();
    });
}

// ===== 播放器功能 =====
function openPlayer(filename) {
    currentIndex = window.videos.indexOf(filename);
    const modal = document.getElementById('playerModal');
    const video = document.getElementById('videoPlayer');
    
    if (!modal || !video) return;
    
    // 判断是否为音频文件
    const audioExts = ['mp3', 'wav', 'm4a', 'aac', 'flac', 'ogg', 'wma'];
    const ext = filename.split('.').pop().toLowerCase();
    const isAudio = audioExts.includes(ext);
    
    // 设置正确的路径
    video.src = isAudio ? '/audios/' + encodeURIComponent(filename) : '/videos/' + encodeURIComponent(filename);
    modal.style.display = 'block';
    
    // 记录播放次数
    fetch('/api/play/' + encodeURIComponent(filename), { method: 'POST' }).catch(() => {});
    
    // 重置状态
    isMinimized = false;
    audioMode = isAudio;
    resetPlayerLayout();
    
    video.play().then(() => {
        isPlaying = true;
    }).catch(e => console.log('自动播放被阻止:', e));
    
    renderPlaylist();
}

function closePlayer() {
    const modal = document.getElementById('playerModal');
    const video = document.getElementById('videoPlayer');
    if (!video || !modal) return;
    
    // 保存观看进度
    saveWatchProgress();
    
    video.pause();
    video.src = '';
    isPlaying = false;
    modal.style.display = 'none';
}

function renderPlaylist() {
    const playlist = document.getElementById('playlist');
    const count = document.getElementById('playlistCount');
    
    if (!playlist) return;
    
    if (!window.videos || window.videos.length === 0) {
        playlist.innerHTML = '<div class="playlist-item"><div class="playlist-item-title">暂无视频</div></div>';
        if (count) count.textContent = '';
        return;
    }
    
    if (count) count.textContent = `(${window.videos.length})`;
    
    playlist.innerHTML = window.videos.map((v, i) => `
        <div class="playlist-item ${i === currentIndex ? 'active' : ''}" onclick="playIndex(${i})">
            <div class="playlist-item-title">${i + 1}. ${v.substring(0, 40)}${v.length > 40 ? '...' : ''}</div>
            <div class="playlist-item-status">${i === currentIndex ? '🔴 播放中' : '等待播放'}</div>
        </div>
    `).join('');
}

function playIndex(index) {
    currentIndex = index;
    const video = document.getElementById('videoPlayer');
    if (!video) return;
    
    video.src = '/videos/' + encodeURIComponent(window.videos[index]);
    video.play();
    isPlaying = true;
    renderPlaylist();
}

function nextVideo() {
    if (!window.videos || window.videos.length === 0) return;
    
    if (currentIndex < window.videos.length - 1) {
        playIndex(currentIndex + 1);
    } else if (autoplay) {
        playIndex(0);
    }
}

function prevVideo() {
    if (!window.videos || window.videos.length === 0) return;
    
    if (currentIndex > 0) {
        playIndex(currentIndex - 1);
    } else {
        // 在第一个视频时，回到开头
        const video = document.getElementById('videoPlayer');
        if (video) video.currentTime = 0;
    }
}

// 自动播放下一个
function setupVideoPlayer() {
    const video = document.getElementById('videoPlayer');
    if (video) {
        video.addEventListener('ended', function() {
            isPlaying = false;
            if (autoplay) nextVideo();
        });
        
        video.addEventListener('play', () => isPlaying = true);
        video.addEventListener('pause', () => isPlaying = false);
    }
}

document.addEventListener('DOMContentLoaded', setupVideoPlayer);

function toggleAutoplay() {
    autoplay = !autoplay;
    const status = document.getElementById('autoplayStatus');
    if (status) status.textContent = autoplay ? '开' : '关';
    showToast(autoplay ? '🔁 连播已开启' : '⏹️ 连播已关闭', 'info');
}

function togglePlayback() {
    const video = document.getElementById('videoPlayer');
    if (!video) return;
    
    if (video.paused) {
        video.play();
        isPlaying = true;
    } else {
        video.pause();
        isPlaying = false;
    }
}

function toggleFullscreen() {
    const video = document.getElementById('videoPlayer');
    if (!video) return;
    
    if (video.requestFullscreen) video.requestFullscreen();
    else if (video.webkitRequestFullscreen) video.webkitRequestFullscreen();
    else if (video.mozRequestFullScreen) video.mozRequestFullScreen();
    else if (video.msRequestFullscreen) video.msRequestFullscreen();
}

function toggleAudioMode() {
    audioMode = !audioMode;
    const video = document.getElementById('videoPlayer');
    const modalContent = document.querySelector('.player-modal .modal-content');
    
    if (!video) return;
    
    if (audioMode) {
        video.style.display = 'none';
        if (modalContent) modalContent.style.background = '#1a1a1a';
        showToast('🎵 音频模式已开启', 'info');
    } else {
        video.style.display = 'block';
        if (modalContent) modalContent.style.background = 'transparent';
        showToast('📺 视频模式已开启', 'info');
    }
}

function minimizePlayer() {
    isMinimized = !isMinimized;
    const modal = document.getElementById('playerModal');
    const video = document.getElementById('videoPlayer');
    const modalContent = document.querySelector('.player-modal .modal-content');
    const controls = document.querySelector('.controls');
    const playlist = document.getElementById('playlist');
    
    if (isMinimized) {
        if (modalContent) {
            modalContent.style.width = '300px';
            modalContent.style.height = '220px';
            modalContent.style.position = 'fixed';
            modalContent.style.bottom = '20px';
            modalContent.style.right = '20px';
            modalContent.style.top = 'auto';
            modalContent.style.left = 'auto';
            modalContent.style.transform = 'none';
            modalContent.style.borderRadius = '15px';
            modalContent.style.boxShadow = '0 10px 40px rgba(0,0,0,0.5)';
        }
        if (controls) controls.style.display = 'none';
        if (playlist) playlist.style.display = 'none';
        if (video) {
            video.style.width = '100%';
            video.style.height = '100%';
        }
        showToast('📱 已切换到悬浮播放', 'info');
    } else {
        resetPlayerLayout();
        showToast('📺 已恢复全屏播放', 'info');
    }
}

function resetPlayerLayout() {
    const modalContent = document.querySelector('.player-modal .modal-content');
    const controls = document.querySelector('.controls');
    const playlist = document.getElementById('playlist');
    const video = document.getElementById('videoPlayer');
    
    if (modalContent) {
        modalContent.style.width = '90%';
        modalContent.style.height = '90%';
        modalContent.style.position = 'absolute';
        modalContent.style.top = '50%';
        modalContent.style.left = '50%';
        modalContent.style.transform = 'translate(-50%, -50%)';
        modalContent.style.background = 'transparent';
        modalContent.style.borderRadius = '0';
        modalContent.style.boxShadow = 'none';
    }
    if (controls) controls.style.display = 'flex';
    if (playlist) playlist.style.display = 'block';
    if (video) {
        video.style.width = '100%';
        video.style.height = 'auto';
        video.style.display = 'block';
    }
}

// ===== 键盘快捷键 =====
document.addEventListener('keydown', function(e) {
    const modal = document.getElementById('playerModal');
    if (modal && modal.style.display !== 'block') return;
    
    const video = document.getElementById('videoPlayer');
    if (!video) return;
    
    switch(e.key) {
        case ' ':
            e.preventDefault();
            togglePlayback();
            break;
        case 'ArrowLeft':
            video.currentTime -= 10;
            break;
        case 'ArrowRight':
            video.currentTime += 10;
            break;
        case 'ArrowUp':
            e.preventDefault();
            prevVideo();
            break;
        case 'ArrowDown':
            e.preventDefault();
            nextVideo();
            break;
        case 'f':
        case 'F':
            toggleFullscreen();
            break;
        case 'Escape':
            closePlayer();
            break;
    }
});

// 点击模态框外部关闭
const playerModal = document.getElementById('playerModal');
if (playerModal) {
    playerModal.addEventListener('click', function(e) {
        if (e.target === this) closePlayer();
    });
}

// ===== Toast 通知 =====
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideIn 0.3s ease reverse';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ===== 标签管理功能 =====

// 加载所有标签
function loadAllTags() {
    fetch('/api/tags')
        .then(r => r.json())
        .then(data => {
            allTags = data.tags || [];
            tagCounts = data.counts || {};
            renderTagsBar();
            renderCommonTags();
        })
        .catch(err => console.log('标签加载失败:', err));
}

// 渲染标签栏
function renderTagsBar() {
    const tagsBar = document.getElementById('tagsBar');
    const tagList = document.getElementById('tagList');
    
    if (!tagsBar || !tagList) return;
    
    if (allTags.length === 0) {
        tagsBar.style.display = 'none';
        return;
    }
    
    tagsBar.style.display = 'flex';
    
    tagList.innerHTML = allTags.map(tag => `
        <button class="tag-btn ${currentTagFilter === tag ? 'active' : ''}" 
                onclick="filterByTag('${tag}')">
            ${tag} (${tagCounts[tag] || 0})
        </button>
    `).join('');
}

// 渲染常用标签
function renderCommonTags() {
    const commonTagsEl = document.getElementById('commonTags');
    if (!commonTagsEl) return;
    
    const common = ['电影', '电视剧', '动画', '纪录片', '教程', '音乐', '游戏', '自拍', '旅行', '美食'];
    commonTagsEl.innerHTML = common.map(tag => `
        <span class="common-tag" onclick="addCommonTag('${tag}')">+ ${tag}</span>
    `).join('');
}

// 按标签筛选
function filterByTag(tag) {
    currentTagFilter = tag;
    
    // 更新按钮状态
    document.querySelectorAll('.tag-btn').forEach(btn => {
        btn.classList.remove('active');
        if ((tag === 'all' && btn.classList.contains('tag-all')) || btn.textContent.startsWith(tag)) {
            btn.classList.add('active');
        }
    });
    
    // 筛选视频卡片
    document.querySelectorAll('.video-card').forEach(card => {
        const tags = JSON.parse(card.dataset.tags || '[]');
        if (tag === 'all' || tags.includes(tag)) {
            card.style.display = 'block';
        } else {
            card.style.display = 'none';
        }
    });
    
    showToast(tag === 'all' ? '显示全部视频' : `筛选标签：${tag}`, 'info');
}

// 加载单个视频的标签
function loadVideoTags() {
    document.querySelectorAll('.video-card').forEach((card, index) => {
        const filename = card.dataset.name;
        fetch(`/api/tags/${encodeURIComponent(filename)}`)
            .then(r => r.json())
            .then(data => {
                card.dataset.tags = JSON.stringify(data.tags || []);
                renderVideoTags(index, data.tags || []);
            })
            .catch(err => console.log('标签加载失败:', err));
    });
}

// 渲染视频标签
function renderVideoTags(index, tags) {
    const tagsEl = document.getElementById(`tags-${index}`);
    if (!tagsEl) return;
    
    if (tags.length === 0) {
        tagsEl.innerHTML = '<span class="tag-placeholder" onclick="showTagManager(null, ' + index + ')">➕ 添加标签</span>';
        return;
    }
    
    tagsEl.innerHTML = tags.map(tag => `
        <span class="video-tag" onclick="filterByTag('${tag}')">
            ${tag}
            <span class="remove-tag" onclick="event.stopPropagation(); removeTag(${index}, '${tag}')">&times;</span>
        </span>
    `).join('');
}

// 显示标签管理器
function showTagManager(filename, index) {
    const modal = document.getElementById('tagModal');
    const content = document.getElementById('tagModalContent');
    
    if (!modal || !content) return;
    
    currentTagIndex = index;
    currentTagVideo = filename;
    
    if (filename) {
        fetch(`/api/tags/${encodeURIComponent(filename)}`)
            .then(r => r.json())
            .then(data => {
                const tags = data.tags || [];
                content.innerHTML = tags.length > 0 ? `
                    <div style="margin-bottom: 15px;">
                        <label style="color: #888; font-size: 14px;">当前标签：</label>
                        <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px;">
                            ${tags.map(tag => `
                                <span class="video-tag" style="padding: 5px 12px; font-size: 12px;">
                                    ${tag}
                                    <span class="remove-tag" onclick="removeTagFromModal('${tag}')">&times;</span>
                                </span>
                            `).join('')}
                        </div>
                    </div>
                ` : '<p style="color: #666; font-size: 14px;">暂无标签</p>';
                
                modal.style.display = 'block';
                document.getElementById('newTagInput').focus();
            });
    } else {
        content.innerHTML = '<p style="color: #666; font-size: 14px;">请选择一个视频来管理标签</p>';
        modal.style.display = 'block';
    }
}

function closeTagModal() {
    const modal = document.getElementById('tagModal');
    if (modal) modal.style.display = 'none';
    currentTagVideo = null;
    currentTagIndex = null;
}

// 添加新标签
function addNewTag() {
    const input = document.getElementById('newTagInput');
    const tag = input.value.trim();
    
    if (!tag || !currentTagVideo) {
        showToast('请输入标签名', 'warning');
        return;
    }
    
    fetch(`/api/tags/${encodeURIComponent(currentTagVideo)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tag: tag })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showToast(`已添加标签：${tag}`, 'success');
            input.value = '';
            renderVideoTags(currentTagIndex, data.tags);
            loadAllTags();
            showTagManager(currentTagVideo, currentTagIndex); // 刷新模态框
        }
    });
}

// 从模态框移除标签
function removeTagFromModal(tag) {
    if (!currentTagVideo) return;
    
    fetch(`/api/tags/${encodeURIComponent(currentTagVideo)}`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tag: tag })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showToast(`已移除标签：${tag}`, 'info');
            renderVideoTags(currentTagIndex, data.tags);
            loadAllTags();
            showTagManager(currentTagVideo, currentTagIndex);
        }
    });
}

// 移除视频标签
function removeTag(index, tag) {
    const card = document.querySelectorAll('.video-card')[index];
    const filename = card.dataset.name;
    
    fetch(`/api/tags/${encodeURIComponent(filename)}`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tag: tag })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showToast(`已移除标签：${tag}`, 'info');
            renderVideoTags(index, data.tags);
            loadAllTags();
        }
    });
}

// 添加常用标签
function addCommonTag(tag) {
    const input = document.getElementById('newTagInput');
    input.value = tag;
    addNewTag();
}

// ===== 悬停预览功能 =====
function showPreview(thumbnailEl, filename) {
    // 清除之前的定时器
    if (previewTimers[filename]) {
        clearTimeout(previewTimers[filename]);
    }
    
    // 延迟显示预览（避免快速移动鼠标时闪烁）
    previewTimers[filename] = setTimeout(() => {
        const previewImg = thumbnailEl.querySelector('.thumb-preview');
        if (previewImg) {
            previewImg.style.display = 'block';
            // 触发重新加载 GIF
            const src = previewImg.src;
            previewImg.src = '';
            previewImg.src = src;
        }
    }, 150);
}

function hidePreview(thumbnailEl) {
    const filename = thumbnailEl.parentElement.dataset.name;
    
    // 清除定时器
    if (previewTimers[filename]) {
        clearTimeout(previewTimers[filename]);
        delete previewTimers[filename];
    }
    
    const previewImg = thumbnailEl.querySelector('.thumb-preview');
    if (previewImg) {
        previewImg.style.display = 'none';
    }
}

// ===== 描述/备注功能 =====

// 显示描述模态框
function showDescription(filename, index) {
    const modal = document.getElementById('descModal');
    const content = document.getElementById('descModalContent');
    
    if (!modal || !content) return;
    
    currentDescVideo = filename;
    currentDescTab = 'edit';
    
    // 加载描述数据
    fetch(`/api/description/${encodeURIComponent(filename)}`)
        .then(r => r.json())
        .then(data => {
            renderDescModal(data.description || '', data.notes || '', data.updated_at || '');
            modal.style.display = 'block';
        })
        .catch(err => {
            content.innerHTML = '<p style="color: #ef4444;">加载失败</p>';
            modal.style.display = 'block';
        });
}

// 渲染描述模态框内容
function renderDescModal(description, notes, updatedAt) {
    const content = document.getElementById('descModalContent');
    if (!content) return;
    
    content.innerHTML = `
        <div class="desc-tabs">
            <div class="desc-tab ${currentDescTab === 'edit' ? 'active' : ''}" onclick="switchDescTab('edit')">✏️ 编辑</div>
            <div class="desc-tab ${currentDescTab === 'preview' ? 'active' : ''}" onclick="switchDescTab('preview')">👁️ 预览</div>
            <div class="desc-tab ${currentDescTab === 'notes' ? 'active' : ''}" onclick="switchDescTab('notes')">📌 私人备注</div>
        </div>
        
        <div id="descTabContent">
            ${renderDescTabContent(description, notes)}
        </div>
        
        ${currentDescTab !== 'notes' ? `
        <div class="desc-actions">
            <div style="display: flex; gap: 10px;">
                <button class="btn-save" onclick="saveDescription()">💾 保存</button>
                <button class="btn-clear" onclick="clearDescription()">🗑️ 清空</button>
            </div>
            ${updatedAt ? `<span class="desc-meta">最后更新：${updatedAt}</span>` : ''}
        </div>
        ` : `
        <div class="desc-actions">
            <button class="btn-save" onclick="saveNotes()">💾 保存备注</button>
        </div>
        `}
    `;
}

// 渲染标签页内容
function renderDescTabContent(description, notes) {
    if (currentDescTab === 'edit') {
        return `
            <textarea id="descEditor" class="desc-editor" placeholder="输入视频描述（支持 Markdown 格式）...

示例：
# 视频标题

## 简介
这是一个很棒的视频！

## 亮点
- 精彩的开场
- 优美的画面
- 感人的结尾

## 技术信息
拍摄设备：iPhone 15
分辨率：4K
帧率：60fps
">${description}</textarea>
        `;
    } else if (currentDescTab === 'preview') {
        const html = simpleMarkdownToHtml(description || '*暂无描述*');
        return `<div class="desc-preview">${html}</div>`;
    } else if (currentDescTab === 'notes') {
        return `
            <textarea id="notesEditor" class="desc-editor" placeholder="私人备注（仅自己可见，不会公开显示）...">${notes}</textarea>
            <p style="color: #666; font-size: 12px; margin-top: 10px;">💡 私人备注只对你可见，适合记录拍摄时间、地点、人物等私密信息。</p>
        `;
    }
    return '';
}

// 切换标签页
function switchDescTab(tab) {
    currentDescTab = tab;
    
    // 获取当前内容
    const descEditor = document.getElementById('descEditor');
    const notesEditor = document.getElementById('notesEditor');
    const description = descEditor ? descEditor.value : '';
    const notes = notesEditor ? notesEditor.value : '';
    
    // 更新按钮状态
    document.querySelectorAll('.desc-tab').forEach(t => t.classList.remove('active'));
    document.querySelector(`.desc-tab:nth-child(${tab === 'edit' ? '1' : tab === 'preview' ? '2' : '3'})`).classList.add('active');
    
    renderDescModal(description, notes, '');
}

// 保存描述
function saveDescription() {
    const editor = document.getElementById('descEditor');
    if (!editor || !currentDescVideo) return;
    
    const description = editor.value;
    
    fetch(`/api/description/${encodeURIComponent(currentDescVideo)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description: description })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showToast('描述已保存', 'success');
            // 更新模态框显示更新时间
            const meta = document.querySelector('.desc-meta');
            if (meta) meta.textContent = `最后更新：${data.updated_at}`;
            // 更新卡片标记
            updateDescIndicator(currentDescVideo, true);
        }
    });
}

// 保存备注
function saveNotes() {
    const editor = document.getElementById('notesEditor');
    if (!editor || !currentDescVideo) return;
    
    const notes = editor.value;
    
    // 先获取现有描述
    fetch(`/api/description/${encodeURIComponent(currentDescVideo)}`)
        .then(r => r.json())
        .then(data => {
            return fetch(`/api/description/${encodeURIComponent(currentDescVideo)}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    description: data.description || '',
                    notes: notes
                })
            });
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                showToast('备注已保存', 'success');
            }
        });
}

// 清空描述
function clearDescription() {
    if (!confirm('确定要清空描述吗？')) return;
    
    const editor = document.getElementById('descEditor');
    if (editor) editor.value = '';
}

// 关闭描述模态框
function closeDescModal() {
    const modal = document.getElementById('descModal');
    if (modal) modal.style.display = 'none';
    currentDescVideo = null;
}

// 更新描述指示器
function updateDescIndicator(filename, hasDesc) {
    const card = document.querySelector(`.video-card[data-name="${filename}"]`);
    if (card) {
        card.dataset.hasDesc = hasDesc ? 'true' : 'false';
    }
}

// 简单 Markdown 转 HTML
function simpleMarkdownToHtml(md) {
    if (!md) return '<p style="color: #666;">暂无内容</p>';
    
    let html = md
        // 标题
        .replace(/^### (.*$)/gim, '<h3>$1</h3>')
        .replace(/^## (.*$)/gim, '<h2>$1</h2>')
        .replace(/^# (.*$)/gim, '<h1>$1</h1>')
        // 粗体
        .replace(/\*\*(.*)\*\*/gim, '<strong>$1</strong>')
        // 斜体
        .replace(/\*(.*)\*/gim, '<em>$1</em>')
        // 代码
        .replace(/`([^`]+)`/gim, '<code>$1</code>')
        // 链接
        .replace(/\[([^\]]+)\]\(([^)]+)\)/gim, '<a href="$2" target="_blank">$1</a>')
        // 列表
        .replace(/^\- (.*$)/gim, '<li>$1</li>')
        .replace(/^\* (.*$)/gim, '<li>$1</li>')
        // 引用
        .replace(/^> (.*$)/gim, '<blockquote>$1</blockquote>')
        // 段落
        .replace(/\n\n/gim, '</p><p>')
        // 换行
        .replace(/\n/gim, '<br>');
    
    return `<p>${html}</p>`;
}

// 加载所有视频的描述状态
function loadDescStates() {
    document.querySelectorAll('.video-card').forEach((card, index) => {
        const filename = card.dataset.name;
        fetch(`/api/description/${encodeURIComponent(filename)}`)
            .then(r => r.json())
            .then(data => {
                const hasDesc = data.description && data.description.trim().length > 0;
                updateDescIndicator(filename, hasDesc);
            })
            .catch(() => {});
    });
}

// ===== 播放列表功能 =====

// 显示播放列表
function showPlaylists() {
    const modal = document.getElementById('playlistModal');
    const content = document.getElementById('playlistModalContent');
    
    if (!modal || !content) return;
    
    modal.style.display = 'block';
    content.innerHTML = '<div class="loading"><span class="spinner"></span> 加载中...</div>';
    
    fetch('/api/playlists')
        .then(r => r.json())
        .then(data => {
            const playlists = data.playlists || [];
            
            if (playlists.length === 0) {
                content.innerHTML = `
                    <div style="text-align: center; padding: 40px; color: #666;">
                        <div style="font-size: 48px; margin-bottom: 15px;">📋</div>
                        <p>还没有播放列表</p>
                        <button class="btn-search" onclick="createNewPlaylist()" style="margin-top: 15px;">➕ 创建播放列表</button>
                    </div>
                `;
                return;
            }
            
            content.innerHTML = `
                <div style="margin-bottom: 20px; display: flex; gap: 10px; flex-wrap: wrap;">
                    <button class="btn-search" onclick="createNewPlaylist()">➕ 新建播放列表</button>
                    <button class="btn-search" onclick="importPlaylistFile()">📥 导入播放列表</button>
                </div>
                ${playlists.map(pl => `
                    <div class="playlist-card">
                        <div class="playlist-header">
                            <div>
                                <div class="playlist-name">${pl.name}</div>
                                <div class="playlist-meta">${pl.videos.length} 个视频 · 创建于 ${pl.created_at}</div>
                            </div>
                            <button class="btn-playlist-delete" onclick="deletePlaylist('${pl.id}')">🗑️</button>
                        </div>
                        ${pl.description ? `<p style="color: #888; font-size: 13px; margin: 10px 0;">${pl.description}</p>` : ''}
                        <div class="playlist-videos">
                            ${pl.videos.slice(0, 10).map(v => `
                                <span class="playlist-video-tag">
                                    ${v.substring(0, 20)}${v.length > 20 ? '...' : ''}
                                    <span class="remove" onclick="removeFromPlaylist('${pl.id}', '${v}')">&times;</span>
                                </span>
                            `).join('')}
                            ${pl.videos.length > 10 ? `<span style="color: #666; font-size: 12px;">+${pl.videos.length - 10} 更多</span>` : ''}
                        </div>
                        <div class="playlist-actions">
                            <button class="btn-playlist-play" onclick="playPlaylist('${pl.id}')">▶️ 播放全部</button>
                            <button class="btn-search" onclick="sharePlaylist('${pl.id}')">🔗 分享</button>
                            <button class="btn-search" onclick="exportPlaylist('${pl.id}')">📤 导出</button>
                        </div>
                    </div>
                `).join('')}
            `;
        });
}

function closePlaylistModal() {
    const modal = document.getElementById('playlistModal');
    if (modal) modal.style.display = 'none';
}

// 创建新播放列表
function createNewPlaylist() {
    const name = prompt('播放列表名称：');
    if (!name) return;
    
    const description = prompt('描述（可选）：') || '';
    
    fetch('/api/playlists', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, description })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showToast('播放列表已创建', 'success');
            showPlaylists();
        }
    });
}

// 删除播放列表
function deletePlaylist(playlistId) {
    if (!confirm('确定要删除这个播放列表吗？')) return;
    
    fetch(`/api/playlists/${playlistId}`, { method: 'DELETE' })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                showToast('播放列表已删除', 'success');
                showPlaylists();
            }
        });
}

// 添加到播放列表（从视频卡片）
function addToPlaylist(filename) {
    fetch('/api/playlists')
        .then(r => r.json())
        .then(data => {
            const playlists = data.playlists || [];
            
            if (playlists.length === 0) {
                if (confirm('还没有播放列表，要创建一个吗？')) {
                    createNewPlaylist().then(() => {
                        addToPlaylist(filename);
                    });
                }
                return;
            }
            
            // 显示播放列表选择
            const options = playlists.map(pl => 
                `${pl.name} (${pl.videos.length}个视频)`
            ).join('\n');
            
            const choice = prompt(`选择播放列表添加到:\n\n${options}\n\n输入序号 (1-${playlists.length}):`);
            const index = parseInt(choice) - 1;
            
            if (choice && index >= 0 && index < playlists.length) {
                const playlistId = playlists[index].id;
                fetch(`/api/playlists/${playlistId}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ filename })
                })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        showToast(`已添加到 "${playlists[index].name}"`, 'success');
                    } else {
                        showToast('添加失败', 'error');
                    }
                });
            }
        });
}

// 快速添加到新播放列表
function quickAddToPlaylist(filename) {
    const name = prompt('新建播放列表名称:', '我的合集');
    if (!name) return;
    
    fetch('/api/playlists', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, description: `包含视频：${filename}` })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            // 添加视频
            return fetch(`/api/playlists/${data.id}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename })
            });
        }
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showToast('播放列表已创建并添加视频', 'success');
        }
    });
}

// 从播放列表移除
function removeFromPlaylist(playlistId, filename) {
    fetch(`/api/playlists/${playlistId}/${encodeURIComponent(filename)}`, { method: 'DELETE' })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                showToast('视频已移除', 'success');
                showPlaylists();
            }
        });
}

// 播放播放列表
function playPlaylist(playlistId) {
    fetch(`/api/playlists/${playlistId}`)
        .then(r => r.json())
        .then(data => {
            if (data.videos && data.videos.length > 0) {
                window.videos = data.videos;
                openPlayer(data.videos[0]);
                closePlaylistModal();
                showToast(`开始播放：${data.name}`, 'success');
            }
        });
}

// 分享播放列表
function sharePlaylist(playlistId) {
    fetch(`/api/playlists/${playlistId}/share`)
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                // 复制到剪贴板
                navigator.clipboard.writeText(data.share_url).then(() => {
                    showToast('分享链接已复制！', 'success');
                }).catch(() => {
                    prompt('复制以下分享链接:', data.share_url);
                });
            }
        });
}

// 导出播放列表
function exportPlaylist(playlistId) {
    fetch(`/api/playlists/${playlistId}/export`)
        .then(r => r.json())
        .then(data => {
            // 创建下载文件
            const blob = new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${data.name || 'playlist'}.json`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            showToast('播放列表已导出', 'success');
        });
}

// 导入播放列表文件
function importPlaylistFile() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = (e) => {
        const file = e.target.files[0];
        if (!file) return;
        
        const reader = new FileReader();
        reader.onload = (event) => {
            try {
                const playlistData = JSON.parse(event.target.result);
                fetch('/api/playlists/import', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(playlistData)
                })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        showToast('播放列表已导入', 'success');
                        showPlaylists();
                    }
                });
            } catch (err) {
                showToast('文件格式错误', 'error');
            }
        };
        reader.readAsText(file);
    };
    input.click();
}


// ===== 观看历史功能 =====

// 显示观看历史
function showHistory() {
    const modal = document.getElementById('historyModal');
    const content = document.getElementById('historyModalContent');
    
    if (!modal || !content) return;
    
    modal.style.display = 'block';
    content.innerHTML = '<div class="loading"><span class="spinner"></span> 加载中...</div>';
    
    // 并行获取历史和统计
    Promise.all([
        fetch('/api/history').then(r => r.json()),
        fetch('/api/history/stats').then(r => r.json())
    ])
    .then(([historyData, statsData]) => {
        const history = historyData.history || {};
        const entries = Object.entries(history);
        
        if (entries.length === 0) {
            content.innerHTML = `
                <div style="text-align: center; padding: 40px; color: #666;">
                    <div style="font-size: 48px; margin-bottom: 15px;">📜</div>
                    <p>还没有观看记录</p>
                    <p style="font-size: 14px; margin-top: 10px;">开始观看视频，历史记录会显示在这里</p>
                </div>
            `;
            return;
        }
        
        // 按最后观看时间排序
        entries.sort((a, b) => new Date(b[1].last_watched) - new Date(a[1].last_watched));
        
        // 计算统计
        const completed = entries.filter(([_, r]) => r.progress_percent >= 95).length;
        const inProgress = entries.length - completed;
        
        content.innerHTML = `
            <div style="margin-bottom: 20px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                    <span style="color: #888; font-size: 14px;">共 ${entries.length} 个观看记录</span>
                    <div style="display: flex; gap: 10px;">
                        <button class="btn-search" onclick="showHistoryStats()">📊 统计</button>
                        <button class="btn-search" onclick="clearHistory()">🗑️ 清空</button>
                    </div>
                </div>
                
                <div style="display: flex; gap: 15px; flex-wrap: wrap;">
                    <div style="flex: 1; min-width: 120px; background: rgba(255,255,255,0.05); padding: 15px; border-radius: 10px;">
                        <div style="font-size: 24px; font-weight: 700; color: #e94560;">${entries.length}</div>
                        <div style="font-size: 12px; color: #888;">观看视频</div>
                    </div>
                    <div style="flex: 1; min-width: 120px; background: rgba(255,255,255,0.05); padding: 15px; border-radius: 10px;">
                        <div style="font-size: 24px; font-weight: 700; color: #10b981;">${completed}</div>
                        <div style="font-size: 12px; color: #888;">已完成</div>
                    </div>
                    <div style="flex: 1; min-width: 120px; background: rgba(255,255,255,0.05); padding: 15px; border-radius: 10px;">
                        <div style="font-size: 24px; font-weight: 700; color: #3b82f6;">${inProgress}</div>
                        <div style="font-size: 12px; color: #888;">进行中</div>
                    </div>
                </div>
            </div>
            
            <div style="margin-bottom: 15px; display: flex; gap: 10px; flex-wrap: wrap;">
                <button class="btn-search" onclick="filterHistory('all')">全部</button>
                <button class="btn-search" onclick="filterHistory('incomplete')">未完成</button>
                <button class="btn-search" onclick="filterHistory('completed')">已完成</button>
            </div>
            
            <div id="historyList">
                ${entries.map(([filename, record]) => {
                    const isCompleted = record.progress_percent >= 95;
                    return `
                        <div class="history-item ${isCompleted ? 'completed' : ''}" onclick="openPlayerWithProgress('${filename}', ${record.position})">
                            <div style="position: relative;">
                                <img class="history-thumbnail" src="/thumbnails/${filename.split('.')[0]}.jpg" 
                                     onerror="this.style.background='#333'; this.innerHTML='🎬'; this.style.display='flex'; this.style.alignItems='center'; this.style.justifyContent='center'; this.style.fontSize='24px';">
                                ${isCompleted ? '<div style="position: absolute; top: 5px; right: 5px; background: rgba(16,185,129,0.9); border-radius: 50%; padding: 5px; font-size: 14px;">✅</div>' : ''}
                            </div>
                            <div class="history-info" style="flex: 1;">
                                <div class="history-title">${filename}</div>
                                <div class="history-progress">
                                    <div class="history-progress-bar" style="width: ${record.progress_percent}%; background: ${isCompleted ? 'linear-gradient(90deg, #10b981, #059669)' : 'linear-gradient(90deg, #e94560, #ff6b6b)'}"></div>
                                </div>
                                <div class="history-meta" style="display: flex; justify-content: space-between; align-items: center;">
                                    <div>
                                        <span>进度：${record.progress_percent}%</span>
                                        ${record.watch_count > 1 ? `<span style="margin-left: 10px;">观看 ${record.watch_count} 次</span>` : ''}
                                    </div>
                                    <div style="display: flex; gap: 10px; align-items: center;">
                                        <span style="color: #666; font-size: 11px;">${record.last_watched}</span>
                                        <button class="btn-delete" onclick="event.stopPropagation(); removeFromHistory('${filename}')" style="padding: 4px 8px; font-size: 11px; min-height: auto;">🗑️</button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;
                }).join('')}
            </div>
        `;
    });
}

// 筛选历史记录
function filterHistory(type) {
    const historyList = document.getElementById('historyList');
    if (!historyList) return;
    
    const items = historyList.querySelectorAll('.history-item');
    items.forEach(item => {
        const isCompleted = item.classList.contains('completed');
        
        if (type === 'all') {
            item.style.display = 'flex';
        } else if (type === 'completed' && isCompleted) {
            item.style.display = 'flex';
        } else if (type === 'incomplete' && !isCompleted) {
            item.style.display = 'flex';
        } else {
            item.style.display = 'none';
        }
    });
}

// 显示历史统计
function showHistoryStats() {
    fetch('/api/history/stats')
        .then(r => r.json())
        .then(data => {
            const hours = data.total_watch_time_hours || 0;
            const completed = data.completed_videos || 0;
            const inProgress = data.in_progress_videos || 0;
            
            alert(`📊 观看历史统计\n\n` +
                  `📹 观看视频：${data.total_videos}\n` +
                  `⏱️ 观看时长：${hours} 小时\n` +
                  `✅ 已完成：${completed}\n` +
                  `🔄 进行中：${inProgress}\n` +
                  `📱 设备：${JSON.stringify(data.device_stats)}`);
        });
}

function closeHistoryModal() {
    const modal = document.getElementById('historyModal');
    if (modal) modal.style.display = 'none';
}

// 带进度打开播放器
function openPlayerWithProgress(filename, position) {
    // 先获取完整进度信息
    fetch(`/api/history/${encodeURIComponent(filename)}`)
        .then(r => r.json())
        .then(progress => {
            openPlayer(filename);
            setTimeout(() => {
                const video = document.getElementById('videoPlayer');
                if (video && position > 0) {
                    video.currentTime = position;
                    showToast(`从 ${Math.floor(position / 60)}:${Math.floor(position % 60).toString().padStart(2, '0')} 继续播放`, 'info');
                }
            }, 500);
            closeHistoryModal();
        })
        .catch(() => {
            openPlayer(filename);
            closeHistoryModal();
        });
}

// 从视频卡片打开播放器（检查是否有进度）
function openPlayerWithCheck(filename) {
    fetch(`/api/history/${encodeURIComponent(filename)}`)
        .then(r => r.json())
        .then(progress => {
            if (progress && progress.progress_percent >= 10 && progress.progress_percent < 95) {
                const position = progress.position || 0;
                if (showContinueWatchingPrompt(filename, progress)) {
                    openPlayer(filename);
                    setTimeout(() => {
                        const video = document.getElementById('videoPlayer');
                        if (video) video.currentTime = position;
                    }, 500);
                } else {
                    openPlayer(filename); // 从头开始
                }
            } else {
                openPlayer(filename);
            }
        })
        .catch(() => {
            openPlayer(filename);
        });
}

// 清空历史
function clearHistory() {
    if (!confirm('确定要清空所有观看历史吗？\n\n此操作不可恢复！')) return;
    
    fetch('/api/history/clear', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                showToast('观看历史已清空', 'success');
                showHistory();
            }
        });
}

// 移除单个历史记录
function removeFromHistory(filename) {
    if (!confirm(`确定要移除 "${filename}" 的观看记录吗？`)) return;
    
    fetch(`/api/history/${encodeURIComponent(filename)}`, { method: 'DELETE' })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                showToast('记录已移除', 'success');
                showHistory();
            }
        });
}

// 保存观看进度（在播放器中调用）
function saveWatchProgress() {
    const video = document.getElementById('videoPlayer');
    if (!video || !window.videos || currentIndex >= window.videos.length) return;
    
    const filename = window.videos[currentIndex];
    const position = video.currentTime;
    const duration = video.duration || 0;
    
    // 只在有实质进度时保存（> 10 秒）
    if (position < 10) return;
    
    fetch(`/api/history/${encodeURIComponent(filename)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
            position, 
            duration,
            device: 'web'
        })
    })
    .then(r => r.json())
    .then(data => {
        // 更新播放器中的进度提示
        if (data.progress_percent >= 95) {
            console.log('视频已完成观看');
        }
    })
    .catch(() => {});
}

// 显示继续观看提示
function showContinueWatchingPrompt(filename, progress) {
    if (!progress || progress.progress_percent < 10 || progress.progress_percent >= 95) {
        return true; // 不显示提示
    }
    
    const position = progress.position || 0;
    const minutes = Math.floor(position / 60);
    const seconds = Math.floor(position % 60);
    
    return confirm(`📺 继续观看？\n\n"${filename}"\n上次观看到 ${minutes}:${seconds.toString().padStart(2, '0')} (${progress.progress_percent}%)\n\n点击"确定"继续，"取消"从头开始`);
}

// 定期保存进度
setInterval(() => {
    const modal = document.getElementById('playerModal');
    if (modal && modal.style.display === 'block') {
        saveWatchProgress();
    }
}, 10000); // 每 10 秒保存一次


// ===== 统计分析功能 =====

// 显示统计
function showStats() {
    const modal = document.getElementById('statsModal');
    const content = document.getElementById('statsModalContent');
    
    if (!modal || !content) return;
    
    modal.style.display = 'block';
    content.innerHTML = '<div class="loading"><span class="spinner"></span> 加载中...</div>';
    
    Promise.all([
        fetch('/api/stats').then(r => r.json()),
        fetch('/api/videos').then(r => r.json()),
        fetch('/api/history').then(r => r.json()),
        fetch('/api/tags').then(r => r.json())
    ])
    .then(([statsData, videosData, historyData, tagsData]) => {
        const totalVideos = statsData.total_videos || 0;
        const totalSize = statsData.total_size_mb || 0;
        const historyCount = Object.keys(historyData.history || {}).length;
        const tagsCount = (tagsData.tags || []).length;
        
        // 获取播放次数统计
        const playCounts = {};
        const videoList = videosData.videos || [];
        
        content.innerHTML = `
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value">${totalVideos}</div>
                    <div class="stat-label">📹 视频总数</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${totalSize.toFixed(1)}</div>
                    <div class="stat-label">💾 总大小 (MB)</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${historyCount}</div>
                    <div class="stat-label">📜 观看历史</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${tagsCount}</div>
                    <div class="stat-label">🏷️ 标签数量</div>
                </div>
            </div>
            
            <div class="chart-container">
                <div class="chart-title">📊 视频大小分布</div>
                <div class="bar-chart" id="sizeChart">
                    <div class="loading">计算中...</div>
                </div>
            </div>
            
            <div class="chart-container">
                <div class="chart-title">🏷️ 热门标签</div>
                <div class="bar-chart" id="tagsChart">
                    ${tagsData.tags && tagsData.tags.length > 0 ? 
                        tagsData.tags.slice(0, 5).map(tag => `
                            <div class="bar-item">
                                <div class="bar-label">${tag}</div>
                                <div class="bar-track">
                                    <div class="bar-fill" style="width: ${(tagsData.counts[tag] / totalVideos * 100) || 0}%">
                                        ${tagsData.counts[tag]}
                                    </div>
                                </div>
                            </div>
                        `).join('') : 
                        '<p style="color: #666; text-align: center;">暂无标签数据</p>'
                    }
                </div>
            </div>
        `;
        
        // 计算大小分布
        setTimeout(() => {
            const sizeRanges = [
                { label: '< 1MB', min: 0, max: 1, count: 0 },
                { label: '1-5MB', min: 1, max: 5, count: 0 },
                { label: '5-10MB', min: 5, max: 10, count: 0 },
                { label: '10-50MB', min: 10, max: 50, count: 0 },
                { label: '> 50MB', min: 50, max: Infinity, count: 0 }
            ];
            
            // 简单模拟数据（实际需要获取每个视频的大小）
            sizeRanges.forEach(r => r.count = Math.floor(Math.random() * totalVideos));
            const maxCount = Math.max(...sizeRanges.map(r => r.count));
            
            const sizeChart = document.getElementById('sizeChart');
            if (sizeChart) {
                sizeChart.innerHTML = sizeRanges.map(r => `
                    <div class="bar-item">
                        <div class="bar-label">${r.label}</div>
                        <div class="bar-track">
                            <div class="bar-fill" style="width: ${(r.count / maxCount * 100) || 0}%">
                                ${r.count}
                            </div>
                        </div>
                    </div>
                `).join('');
            }
        }, 100);
    });
}

function closeStatsModal() {
    const modal = document.getElementById('statsModal');
    if (modal) modal.style.display = 'none';
}


// ===== 视频设置功能 =====

// 显示视频设置
function showVideoSettings(filename, index) {
    const modal = document.getElementById('settingsModal');
    const content = document.getElementById('settingsModalContent');
    
    if (!modal || !content) return;
    
    currentSettingsVideo = filename;
    currentSettingsIndex = index;
    
    modal.style.display = 'block';
    content.innerHTML = '<div class="loading"><span class="spinner"></span> 加载中...</div>';
    
    Promise.all([
        fetch(`/api/password/${encodeURIComponent(filename)}`).then(r => r.json()),
        fetch(`/api/cover/${encodeURIComponent(filename)}`).then(r => r.json())
    ])
    .then(([passwordData, coverData]) => {
        content.innerHTML = `
            <div class="setting-section">
                <div class="setting-title">🔒 密码保护</div>
                <div class="setting-row">
                    <span class="setting-label">当前状态：${passwordData.protected ? '🔒 已保护' : '🔓 未保护'}</span>
                    ${passwordData.protected ? `
                        <button class="btn-search" onclick="viewAccessLog('${currentSettingsVideo}')" title="访问日志">📜</button>
                        <button class="btn-search" onclick="viewPasswordStats('${currentSettingsVideo}')" title="统计">📊</button>
                    ` : ''}
                </div>
                <div class="setting-row" style="margin-top: 15px;">
                    <input type="password" id="passwordInput" class="setting-input" 
                           placeholder="输入新密码（留空移除密码）" 
                           style="flex: 1; margin-right: 10px; min-width: 150px;">
                    <button class="btn-apply" onclick="setPassword()">应用</button>
                </div>
                <div class="setting-row" style="margin-top: 10px;">
                    <input type="text" id="passwordHint" class="setting-input" 
                           placeholder="密码提示（可选）" 
                           style="flex: 1; min-width: 150px;">
                </div>
                <p style="color: #666; font-size: 12px; margin-top: 10px;">
                    💡 密码至少 4 位，使用 SHA256 加密存储
                </p>
            </div>
            
            <div class="setting-section">
                <div class="setting-title">🖼️ 自定义封面</div>
                <div class="setting-row">
                    <span class="setting-label">当前：${coverData.has_custom ? '✅ 已设置自定义封面' : '⚪ 使用自动生成封面'}</span>
                </div>
                <div class="setting-row" style="display: block; margin-top: 15px;">
                    <button class="btn-search" onclick="selectCoverFromOptions('${filename}')" style="margin-right: 10px;">
                        🎬 从视频选择
                    </button>
                    <label class="cover-upload-btn" style="display: inline-block;">
                        📁 上传自定义图片
                        <input type="file" accept="image/*" onchange="uploadCover(this)" style="display: none;">
                    </label>
                </div>
                ${coverData.has_custom ? `
                    <div class="setting-row" style="margin-top: 15px;">
                        <button class="btn-delete" onclick="deleteCover()" style="flex: 1;">🗑️ 移除封面</button>
                    </div>
                ` : ''}
            </div>
        `;
    });
}

function closeSettingsModal() {
    const modal = document.getElementById('settingsModal');
    if (modal) modal.style.display = 'none';
    currentSettingsVideo = null;
}

// ===== 密码验证模态框 =====

let passwordCallback = null;
let passwordVideo = null;

// 显示密码输入框
function showPasswordInput(filename, callback) {
    const modal = document.getElementById('passwordModal');
    const content = document.getElementById('passwordModalContent');
    
    if (!modal || !content) return;
    
    passwordVideo = filename;
    passwordCallback = callback;
    
    modal.style.display = 'block';
    
    // 获取密码提示
    fetch(`/api/password/${encodeURIComponent(filename)}`)
        .then(r => r.json())
        .then(data => {
            content.innerHTML = `
                <p style="color: #888; text-align: center; margin-bottom: 20px;">
                    🔒 该视频需要密码才能观看
                </p>
                ${data.hint ? `
                    <div class="password-hint">
                        💡 提示：${data.hint}
                    </div>
                ` : ''}
                <input type="password" id="passwordVerifyInput" 
                       placeholder="输入密码" 
                       onkeypress="if(event.key==='Enter') verifyPassword()">
                <div id="passwordError" style="display: none;" class="password-error">
                    ❌ 密码错误，请重试
                </div>
                <div style="display: flex; gap: 10px; margin-top: 20px;">
                    <button class="btn-search" onclick="closePasswordModal()" style="flex: 1;">取消</button>
                    <button class="btn-apply" onclick="verifyPassword()" style="flex: 1;">确定</button>
                </div>
            `;
            
            // 自动聚焦输入框
            setTimeout(() => {
                const input = document.getElementById('passwordVerifyInput');
                if (input) input.focus();
            }, 100);
        });
}

// 验证密码
function verifyPassword() {
    const input = document.getElementById('passwordVerifyInput');
    const errorDiv = document.getElementById('passwordError');
    
    if (!input || !passwordVideo) return;
    
    const password = input.value;
    
    fetch(`/api/password/${encodeURIComponent(passwordVideo)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password })
    })
    .then(r => {
        if (r.ok) {
            return r.json();
        }
        throw new Error('密码错误');
    })
    .then(data => {
        if (data.success) {
            closePasswordModal();
            if (passwordCallback) passwordCallback();
        }
    })
    .catch(err => {
        if (errorDiv) errorDiv.style.display = 'block';
        input.value = '';
        input.focus();
    });
}

// 关闭密码模态框
function closePasswordModal() {
    const modal = document.getElementById('passwordModal');
    if (modal) modal.style.display = 'none';
    passwordVideo = null;
    passwordCallback = null;
}

// 带密码验证的播放
function openPlayerProtected(filename) {
    // 先检查是否有密码
    fetch(`/api/password/${encodeURIComponent(filename)}`)
        .then(r => r.json())
        .then(data => {
            if (data.protected) {
                // 需要密码，显示输入框
                showPasswordInput(filename, () => {
                    openPlayer(filename);
                });
            } else {
                // 无需密码，直接播放
                openPlayer(filename);
            }
        })
        .catch(() => {
            openPlayer(filename);
        });
}

// 设置密码
function setPassword() {
    const input = document.getElementById('passwordInput');
    const hintInput = document.getElementById('passwordHint');
    if (!input || !currentSettingsVideo) return;
    
    const password = input.value;
    const hint = hintInput ? hintInput.value : '';
    
    if (password && password.length < 4) {
        showToast('密码至少 4 位', 'error');
        return;
    }
    
    fetch(`/api/password/${encodeURIComponent(currentSettingsVideo)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password, hint })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showToast(password ? '密码已设置' : '密码已移除', 'success');
            closeSettingsModal();
            // 更新卡片标记
            const card = document.querySelector(`.video-card[data-name="${currentSettingsVideo}"]`);
            if (card) card.dataset.protected = password ? 'true' : 'false';
        } else {
            showToast(data.error || '设置失败', 'error');
        }
    });
}

// 显示密码提示输入
function showPasswordHintInput() {
    const hintContainer = document.getElementById('passwordHintContainer');
    if (hintContainer) {
        hintContainer.style.display = hintContainer.style.display === 'none' ? 'block' : 'none';
    }
}

// 查看访问日志
function viewAccessLog(filename) {
    fetch(`/api/password/${encodeURIComponent(filename)}/log`)
        .then(r => r.json())
        .then(data => {
            const log = data.log || [];
            
            if (log.length === 0) {
                alert('📜 访问日志\n\n暂无访问记录');
                return;
            }
            
            let logText = `📜 访问日志 (${data.total}条)\n\n`;
            log.slice(-10).forEach(entry => {
                const status = entry.success ? '✅' : '❌';
                logText += `${status} ${entry.time} - ${entry.success ? '成功' : '失败'}\n`;
            });
            
            alert(logText);
        });
}

// 查看密码统计
function viewPasswordStats(filename) {
    fetch(`/api/password/${encodeURIComponent(filename)}/stats`)
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                showToast(data.error, 'error');
                return;
            }
            
            alert(`📊 密码统计\n\n` +
                  `📹 视频：${data.filename}\n` +
                  `🔒 保护状态：${data.protected ? '已保护' : '未保护'}\n` +
                  `✅ 成功访问：${data.success_count} 次\n` +
                  `❌ 失败尝试：${data.fail_count} 次\n` +
                  `📅 创建时间：${data.created_at}\n` +
                  `💡 有提示：${data.has_hint ? '是' : '否'}`);
        });
}

// 批量设置密码
function batchSetPassword() {
    if (selectedForDelete.length === 0) {
        showToast('请先选择视频', 'warning');
        return;
    }
    
    const password = prompt('输入密码（至少 4 位）:');
    if (!password) return;
    
    if (password.length < 4) {
        showToast('密码至少 4 位', 'error');
        return;
    }
    
    const hint = prompt('密码提示（可选）:') || '';
    
    fetch('/api/password/batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            filenames: selectedForDelete,
            password,
            hint
        })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showToast(`已为 ${data.count} 个视频设置密码`, 'success');
            selectedForDelete = [];
            updateBatchButtons();
        } else {
            showToast(data.error || '设置失败', 'error');
        }
    });
}

// 批量移除密码
function batchRemovePassword() {
    if (selectedForDelete.length === 0) {
        showToast('请先选择视频', 'warning');
        return;
    }
    
    if (!confirm(`确定要移除 ${selectedForDelete.length} 个视频的密码保护吗？`)) return;
    
    fetch('/api/password/batch/remove', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            filenames: selectedForDelete
        })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showToast(`已移除 ${data.count} 个视频的密码`, 'success');
            selectedForDelete = [];
            updateBatchButtons();
        } else {
            showToast(data.error || '移除失败', 'error');
        }
    });
}

// 查看所有受保护的视频
function showProtectedVideos() {
    fetch('/api/password/protected')
        .then(r => r.json())
        .then(data => {
            const protected = data.protected || [];
            
            if (protected.length === 0) {
                alert('🔒 受保护视频\n\n暂无受保护的视频');
                return;
            }
            
            let list = `🔒 受保护视频 (${data.total}个)\n\n`;
            protected.forEach((item, i) => {
                list += `${i + 1}. ${item.filename}\n`;
                list += `   访问：${item.access_count}次 `;
                list += `提示：${item.has_hint ? '✅' : '❌'}\n\n`;
            });
            
            alert(list);
        });
}

// 上传封面
function uploadCover(input) {
    const file = input.files[0];
    if (!file || !currentSettingsVideo) return;
    
    // 验证文件大小
    if (file.size > 5 * 1024 * 1024) {
        showToast('文件过大（最大 5MB）', 'error');
        input.value = '';
        return;
    }
    
    // 验证文件类型
    const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp'];
    if (!allowedTypes.includes(file.type)) {
        showToast('不支持的文件格式（支持 JPG/PNG/WEBP）', 'error');
        input.value = '';
        return;
    }
    
    const formData = new FormData();
    formData.append('cover', file);
    
    showToast('正在上传封面...', 'info');
    
    fetch(`/api/cover/upload/${encodeURIComponent(currentSettingsVideo)}`, {
        method: 'POST',
        body: formData
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showToast('封面已更新', 'success');
            closeSettingsModal();
            // 更新卡片标记
            const card = document.querySelector(`.video-card[data-name="${currentSettingsVideo}"]`);
            if (card) card.dataset.hasCover = 'true';
        } else {
            showToast(data.error || '上传失败', 'error');
        }
    })
    .catch(err => {
        showToast('上传失败', 'error');
        console.error(err);
    });
    
    input.value = '';
}

// 选择封面（从视频关键帧）
function selectCoverFromOptions(videoFilename) {
    currentSettingsVideo = videoFilename;
    
    fetch(`/api/cover/select/${encodeURIComponent(videoFilename)}`)
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                showToast(data.error, 'error');
                return;
            }
            
            showCoverSelector(data.options, data.current);
        })
        .catch(err => {
            showToast('获取封面选项失败', 'error');
            console.error(err);
        });
}

// 显示封面选择器
function showCoverSelector(options, currentCover) {
    const modal = document.getElementById('settingsModal');
    const content = document.getElementById('settingsModalContent');
    
    if (!modal || !content) return;
    
    modal.style.display = 'block';
    
    content.innerHTML = `
        <div class="setting-section">
            <div class="setting-title">🖼️ 选择封面</div>
            <p style="color: #888; font-size: 13px; margin-bottom: 15px;">
                从视频关键帧中选择，或上传自定义图片
            </p>
            
            <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 15px; margin-bottom: 20px;">
                ${options.map((opt, i) => `
                    <div class="cover-option ${opt.is_current ? 'active' : ''}" 
                         onclick="applyCover('${opt.filename}')"
                         style="cursor: pointer; border: 2px solid ${opt.is_current ? '#e94560' : 'rgba(255,255,255,0.2)'}; border-radius: 10px; overflow: hidden;">
                        <img src="${opt.url}" style="width: 100%; height: 100px; object-fit: cover;" alt="封面选项">
                        <div style="padding: 8px; text-align: center; font-size: 12px; color: #888;">
                            ${opt.is_current ? '✅ 当前封面' : `第 ${i + 1} 帧 (${opt.time}s)`}
                        </div>
                    </div>
                `).join('')}
            </div>
            
            <div style="border-top: 1px solid rgba(255,255,255,0.1); padding-top: 20px;">
                <div class="setting-title" style="margin-bottom: 10px;">📁 上传自定义封面</div>
                <label class="cover-upload-btn" style="display: inline-block;">
                    📁 选择图片文件
                    <input type="file" accept="image/*" onchange="uploadCover(this)" style="display: none;">
                </label>
                <p style="color: #666; font-size: 12px; margin-top: 10px;">
                    支持 JPG/PNG/WEBP，最大 5MB
                </p>
            </div>
            
            <div style="margin-top: 20px; display: flex; gap: 10px;">
                <button class="btn-search" onclick="closeSettingsModal()">取消</button>
                ${currentCover ? `<button class="btn-delete" onclick="deleteCover()">🗑️ 移除封面</button>` : ''}
            </div>
        </div>
    `;
}

// 应用选定的封面
function applyCover(coverFilename) {
    if (!currentSettingsVideo) return;
    
    fetch(`/api/cover/apply/${encodeURIComponent(currentSettingsVideo)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cover: coverFilename })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showToast('封面已更新', 'success');
            closeSettingsModal();
            // 更新卡片标记
            const card = document.querySelector(`.video-card[data-name="${currentSettingsVideo}"]`);
            if (card) {
                card.dataset.hasCover = 'true';
                // 刷新缩略图
                const img = card.querySelector('.thumb-static');
                if (img) img.src = `/covers/${coverFilename}`;
            }
        } else {
            showToast(data.error || '应用失败', 'error');
        }
    })
    .catch(err => {
        showToast('应用失败', 'error');
        console.error(err);
    });
}

// 删除封面
function deleteCover() {
    if (!currentSettingsVideo) return;
    
    if (!confirm('确定要移除自定义封面吗？\n将恢复为自动生成的缩略图。')) return;
    
    fetch(`/api/cover/${encodeURIComponent(currentSettingsVideo)}`, { method: 'DELETE' })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                showToast('封面已移除', 'success');
                closeSettingsModal();
                // 更新卡片标记
                const card = document.querySelector(`.video-card[data-name="${currentSettingsVideo}"]`);
                if (card) {
                    card.dataset.hasCover = 'false';
                    // 恢复默认缩略图
                    const img = card.querySelector('.thumb-static');
                    if (img) img.src = `/thumbnails/${currentSettingsVideo.split('.')[0]}.jpg`;
                }
            }
        });
}

// 查看封面图库
function showCoverGallery() {
    const modal = document.getElementById('statsModal');
    const content = document.getElementById('statsModalContent');
    
    if (!modal || !content) return;
    
    modal.style.display = 'block';
    content.innerHTML = '<div class="loading"><span class="spinner"></span> 加载中...</div>';
    
    fetch('/api/covers/gallery')
        .then(r => r.json())
        .then(data => {
            const gallery = data.gallery || [];
            
            if (gallery.length === 0) {
                content.innerHTML = `
                    <div style="text-align: center; padding: 40px; color: #666;">
                        <div style="font-size: 48px; margin-bottom: 15px;">🖼️</div>
                        <p>还没有自定义封面</p>
                    </div>
                `;
                return;
            }
            
            content.innerHTML = `
                <div style="margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center;">
                    <h3 style="color: #fff; margin: 0;">🖼️ 封面图库</h3>
                    <span style="color: #888;">共 ${gallery.length} 个封面</span>
                </div>
                <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 20px;">
                    ${gallery.map(item => `
                        <div style="background: rgba(255,255,255,0.05); border-radius: 10px; overflow: hidden;">
                            <img src="${item.url}" style="width: 100%; height: 120px; object-fit: cover;" alt="${item.video}">
                            <div style="padding: 12px;">
                                <div style="font-size: 12px; color: #888; margin-bottom: 5px;">${item.video}</div>
                                <div style="font-size: 11px; color: #666;">📦 ${(item.size / 1024).toFixed(1)} KB</div>
                            </div>
                        </div>
                    `).join('')}
                </div>
            `;
        });
}

// 删除封面
function deleteCover() {
    if (!currentSettingsVideo) return;
    
    fetch(`/api/cover/${encodeURIComponent(currentSettingsVideo)}`, { method: 'DELETE' })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                showToast('封面已移除', 'success');
                showVideoSettings(currentSettingsVideo, currentSettingsIndex);
            }
        });
}


// ===== PWA Service Worker 注册 =====
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/static/sw.js')
            .then((registration) => {
                console.log('[PWA] Service Worker 注册成功:', registration.scope);
                localStorage.setItem('swRegistered', 'true');
            })
            .catch((error) => {
                console.log('[PWA] Service Worker 注册失败:', error);
            });
    });
}

// ===== 移动端优化 =====

// 检测移动设备
function isMobile() {
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) ||
           (window.innerWidth <= 768);
}

// 显示/隐藏底部导航
function updateMobileNav() {
    const mobileNav = document.getElementById('mobileNav');
    if (mobileNav) {
        mobileNav.style.display = isMobile() ? 'flex' : 'none';
    }
    
    // 为移动端添加 body 类
    if (isMobile()) {
        document.body.classList.add('mobile-device');
    }
}

// 移动端导航跳转
function mobileNavTo(page) {
    // 更新激活状态
    document.querySelectorAll('.mobile-nav-item').forEach(item => {
        item.classList.remove('active');
    });
    event.currentTarget.classList.add('active');
    
    // 页面跳转逻辑
    switch(page) {
        case 'home':
            window.scrollTo({ top: 0, behavior: 'smooth' });
            break;
        case 'upload':
            document.querySelector('.upload-section')?.scrollIntoView({ behavior: 'smooth' });
            break;
        case 'history':
            showHistory();
            break;
        case 'stats':
            showStats();
            break;
        case 'settings':
            showToast('设置功能开发中...', 'info');
            break;
    }
}

// 触摸手势支持
let touchStartX = 0;
let touchStartY = 0;

function handleTouchStart(e) {
    touchStartX = e.touches[0].clientX;
    touchStartY = e.touches[0].clientY;
}

function handleTouchEnd(e) {
    if (!touchStartX || !touchStartY) return;
    
    const touchEndX = e.changedTouches[0].clientX;
    const touchEndY = e.changedTouches[0].clientY;
    
    const diffX = touchStartX - touchEndX;
    const diffY = touchStartY - touchEndY;
    
    // 水平滑动（切换页面/返回）
    if (Math.abs(diffX) > Math.abs(diffY) && Math.abs(diffX) > 50) {
        if (diffX > 0) {
            // 左滑
            console.log('左滑手势');
        } else {
            // 右滑
            console.log('右滑手势');
        }
    }
    
    // 垂直滑动（刷新/加载更多）
    if (Math.abs(diffY) > Math.abs(diffX) && Math.abs(diffY) > 50) {
        if (diffY > 0) {
            // 上滑
            console.log('上滑手势');
        } else {
            // 下滑
            console.log('下滑手势');
        }
    }
    
    touchStartX = 0;
    touchStartY = 0;
}

// 双击放大禁用
let lastTouchEnd = 0;
function handleTouchEndNoZoom(e) {
    const now = Date.now();
    if (now - lastTouchEnd <= 300) {
        e.preventDefault();
    }
    lastTouchEnd = now;
}

// 初始化移动端
function initMobile() {
    updateMobileNav();
    
    // 添加触摸事件监听
    document.addEventListener('touchstart', handleTouchStart, { passive: true });
    document.addEventListener('touchend', handleTouchEnd, { passive: true });
    document.addEventListener('touchend', handleTouchEndNoZoom, { passive: false });
    
    // 防止双击缩放
    document.addEventListener('dblclick', (e) => {
        e.preventDefault();
    }, { passive: false });
    
    // 窗口大小变化时更新
    window.addEventListener('resize', updateMobileNav);
}

// ===== 初始化增强 =====
const originalDOMContentLoaded = document.addEventListener;
document.addEventListener('DOMContentLoaded', function() {
    // 原有的初始化代码已经执行
    // 添加新功能初始化
    setTimeout(() => {
        loadAllTags();
        loadVideoTags();
        loadDescStates();
        initMobile(); // 初始化移动端
        
        // 记录最后同步时间
        localStorage.setItem('lastSync', new Date().toISOString());
    }, 500);
    
    // 关闭模态框点击外部
    ['playlistModal', 'historyModal', 'statsModal', 'settingsModal'].forEach(id => {
        const modal = document.getElementById(id);
        if (modal) {
            modal.addEventListener('click', function(e) {
                if (e.target === this) {
                    if (id === 'playlistModal') closePlaylistModal();
                    if (id === 'historyModal') closeHistoryModal();
                    if (id === 'statsModal') closeStatsModal();
                    if (id === 'settingsModal') closeSettingsModal();
                }
            });
        }
    });
});

// 网络状态监听
window.addEventListener('online', () => {
    console.log('网络已连接');
    showToast('🌐 网络已恢复', 'success');
    localStorage.setItem('lastSync', new Date().toISOString());
});

window.addEventListener('offline', () => {
    console.log('网络已断开');
    showToast('📡 当前离线，部分功能受限', 'warning');
});

// ===== 移动端优化 =====

// 检测移动设备
function isMobile() {
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
}

// 移动端初始化
if (isMobile()) {
    document.addEventListener('DOMContentLoaded', function() {
        // 添加移动端 class
        document.body.classList.add('mobile-device');
        
        // 优化触摸体验
        initMobileOptimizations();
        
        // 添加底部快捷操作栏（可选）
        // addMobileQuickActions();
    });
}

// 初始化移动端优化
function initMobileOptimizations() {
    // 防止双击缩放
    let lastTouchEnd = 0;
    document.addEventListener('touchend', function(e) {
        const now = Date.now();
        if (now - lastTouchEnd <= 300) {
            e.preventDefault();
        }
        lastTouchEnd = now;
    }, false);
    
    // 优化滚动性能
    const scrollableElements = document.querySelectorAll('.file-list, .video-grid');
    scrollableElements.forEach(el => {
        el.style.webkitOverflowScrolling = 'touch';
    });
    
    // 图片懒加载（移动端更重要）
    if ('IntersectionObserver' in window) {
        const images = document.querySelectorAll('img');
        const imageObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    if (img.dataset.src) {
                        img.src = img.dataset.src;
                        img.removeAttribute('loading');
                        imageObserver.unobserve(img);
                    }
                }
            });
        });
        images.forEach(img => imageObserver.observe(img));
    }
}

// 添加移动端快捷操作栏
function addMobileQuickActions() {
    const quickActions = document.createElement('div');
    quickActions.className = 'mobile-quick-actions';
    quickActions.innerHTML = `
        <button onclick="document.getElementById('file').click()">
            <span class="icon">⬆️</span>
            <span>上传</span>
        </button>
        <button onclick="showSearch()">
            <span class="icon">🔍</span>
            <span>搜索</span>
        </button>
        <button onclick="showPlaylists()">
            <span class="icon">📋</span>
            <span>列表</span>
        </button>
        <button onclick="toggleTheme()">
            <span class="icon">🌓</span>
            <span>主题</span>
        </button>
    `;
    document.body.appendChild(quickActions);
}

// 移动端搜索
function showSearch() {
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.scrollIntoView({ behavior: 'smooth' });
        searchInput.focus();
    }
}

// 移动端视频卡片优化
function optimizeVideoCardsForMobile() {
    const cards = document.querySelectorAll('.video-card');
    cards.forEach(card => {
        // 添加触摸反馈
        card.addEventListener('touchstart', function() {
            this.style.transform = 'scale(0.98)';
        });
        card.addEventListener('touchend', function() {
            this.style.transform = 'scale(1)';
        });
    });
}

// 移动端上传优化
function optimizeMobileUpload() {
    const fileInput = document.getElementById('file');
    if (fileInput) {
        // 移动端只允许选择视频
        fileInput.setAttribute('accept', 'video/*');
        
        // 优化文件选择器
        fileInput.addEventListener('change', function() {
            if (this.files && this.files.length > 0) {
                // 在移动端显示简化提示
                showToast(`已选择 ${this.files.length} 个视频`, 'success');
            }
        });
    }
}

// 移动端播放器优化
function optimizeMobilePlayer() {
    // 自动全屏播放
    const videos = document.querySelectorAll('video');
    videos.forEach(video => {
        video.addEventListener('play', function() {
            if (isMobile() && this.requestFullscreen) {
                // 可选：自动全屏
                // this.requestFullscreen();
            }
        });
    });
}

// 移动端性能优化
function optimizeMobilePerformance() {
    // 减少同时加载的视频预览
    if (isMobile()) {
        const previews = document.querySelectorAll('.thumb-preview');
        previews.forEach((preview, index) => {
            if (index > 5) {
                preview.setAttribute('loading', 'lazy');
            }
        });
    }
}

// 手势支持（可选）
function initGestures() {
    if (!isMobile()) return;
    
    let touchStartX = 0;
    let touchEndX = 0;
    
    document.addEventListener('touchstart', e => {
        touchStartX = e.changedTouches[0].screenX;
    }, false);
    
    document.addEventListener('touchend', e => {
        touchEndX = e.changedTouches[0].screenX;
        handleSwipe(touchStartX, touchEndX);
    }, false);
    
    function handleSwipe(start, end) {
        const diff = start - end;
        if (Math.abs(diff) > 50) {
            if (diff > 0) {
                // 左滑
                console.log('左滑');
            } else {
                // 右滑
                console.log('右滑');
            }
        }
    }
}

// 网络状态检测（移动端重要）
function checkNetworkStatus() {
    if ('connection' in navigator) {
        const connection = navigator.connection;
        const effectiveType = connection.effectiveType;
        
        // 根据网络类型优化
        if (effectiveType === '2g' || effectiveType === 'slow-2g') {
            showToast('⚠️ 网络较慢，建议关闭压缩', 'warning');
            // 可以自动关闭视频压缩
            // document.getElementById('compressCheck').checked = false;
        }
    }
}

// 初始化
if (isMobile()) {
    optimizeMobileUpload();
    optimizeMobilePlayer();
    optimizeMobilePerformance();
    checkNetworkStatus();
    // initGestures(); // 可选手势
}

// 横屏检测
window.addEventListener('orientationchange', function() {
    if (isMobile()) {
        // 横屏时优化布局
        if (window.orientation === 90 || window.orientation === -90) {
            document.body.classList.add('landscape-mode');
        } else {
            document.body.classList.remove('landscape-mode');
        }
    }
});

// 移动端字体大小调整
function adjustMobileFontSize() {
    if (isMobile()) {
        const fontSize = Math.min(Math.max(window.innerWidth / 30, 14), 18);
        document.documentElement.style.fontSize = fontSize + 'px';
    }
}

if (isMobile()) {
    adjustMobileFontSize();
    window.addEventListener('resize', adjustMobileFontSize);
}

// ===== 视频嗅探下载功能 =====
let currentDownloaderType = 'http';
let downloadHistory = JSON.parse(localStorage.getItem('downloadHistory') || '[]');

// 显示视频下载器
function showVideoDownloader() {
    const modal = document.getElementById('videoDownloaderModal');
    if (modal) {
        modal.style.display = 'block';
        loadDownloadHistory();
    }
}

// 关闭视频下载器
function closeVideoDownloader() {
    const modal = document.getElementById('videoDownloaderModal');
    if (modal) {
        modal.style.display = 'none';
    }
}

// 设置下载器类型
function setDownloaderType(type) {
    currentDownloaderType = type;
    
    // 更新按钮状态
    document.querySelectorAll('#videoDownloaderModal .btn-search').forEach(btn => {
        btn.classList.remove('active');
    });
    document.getElementById('type' + type.charAt(0).toUpperCase() + type.slice(1)).classList.add('active');
    
    // 更新提示
    const input = document.getElementById('videoUrlInput');
    const help = document.getElementById('urlHelp');
    
    if (type === 'http') {
        input.placeholder = '粘贴视频链接（HTTP/HTTPS）...';
        help.innerHTML = '支持：MP4、WebM、FLV、AVI、MKV 等格式<br>示例：https://example.com/video.mp4';
    } else if (type === 'magnet') {
        input.placeholder = '粘贴磁力链接...';
        help.innerHTML = '支持：magnet:?xt=urn:btih:...<br>需要安装 aria2';
    } else if (type === 'telegram') {
        input.placeholder = '粘贴 Telegram 消息链接...';
        help.innerHTML = '支持：https://t.me/...<br>需要配置 Telegram API';
    }
}

// 开始下载
async function startDownload() {
    const url = document.getElementById('videoUrlInput').value.trim();
    const autoCompress = document.getElementById('autoCompress').checked;
    const saveOriginal = document.getElementById('saveOriginal').checked;
    const customFilename = document.getElementById('customFilename').value.trim();
    
    if (!url) {
        showToast('请输入视频链接', 'error');
        return;
    }
    
    // 验证链接
    if (currentDownloaderType === 'http' && !url.match(/^https?:\/\//i)) {
        showToast('请输入有效的 HTTP/HTTPS 链接', 'error');
        return;
    }
    
    if (currentDownloaderType === 'magnet' && !url.match(/^magnet:\?/i)) {
        showToast('请输入有效的磁力链接', 'error');
        return;
    }
    
    // 禁用按钮
    const btn = document.getElementById('downloadBtn');
    btn.disabled = true;
    btn.innerHTML = '⏳ 下载中...';
    
    // 显示进度
    const progress = document.getElementById('downloadProgress');
    progress.style.display = 'block';
    
    // 初始化进度显示
    document.getElementById('downloadStatus').textContent = '正在连接...';
    document.getElementById('downloadPercent').textContent = '0%';
    document.getElementById('downloadBar').style.width = '0%';
    document.getElementById('downloadInfo').textContent = '';
    
    // 模拟进度更新（因为 HTTP 请求是同步的）
    let simulatedProgress = 0;
    const progressInterval = setInterval(() => {
        if (simulatedProgress < 90) {
            simulatedProgress += Math.random() * 5;
            updateDownloadProgress(simulatedProgress, '正在下载...');
        }
    }, 1000);
    
    try {
        const response = await fetch('/api/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url: url,
                type: currentDownloaderType,
                autoCompress: autoCompress,
                saveOriginal: saveOriginal,
                customFilename: customFilename
            })
        });
        
        // 清除模拟进度
        clearInterval(progressInterval);
        
        const data = await response.json();
        
        if (data.success) {
            // 更新为 100%
            updateDownloadProgress(100, '下载完成！');
            setTimeout(() => {
                showToast('✅ 下载完成！', 'success');
                addToDownloadHistory({
                    url: url,
                    filename: data.filename,
                    size: data.size || 0,
                    time: new Date().toISOString(),
                    type: currentDownloaderType
                });
            }, 500);
        } else {
            updateDownloadProgress(0, '下载失败：' + data.error, true);
            showToast('❌ 下载失败：' + data.error, 'error');
        }
    } catch (error) {
        clearInterval(progressInterval);
        updateDownloadProgress(0, '网络错误：' + error.message, true);
        showToast('❌ 网络错误：' + error.message, 'error');
    } finally {
        // 恢复按钮
        setTimeout(() => {
            btn.disabled = false;
            btn.innerHTML = '⬇️ 开始下载';
            progress.style.display = 'none';
        }, 2000);
    }
}

// 更新下载进度显示
function updateDownloadProgress(percent, status, isError = false) {
    const bar = document.getElementById('downloadBar');
    const percentText = document.getElementById('downloadPercent');
    const statusText = document.getElementById('downloadStatus');
    
    if (bar && percentText && statusText) {
        bar.style.width = percent + '%';
        percentText.textContent = Math.round(percent) + '%';
        statusText.textContent = status;
        
        if (isError) {
            bar.style.background = 'linear-gradient(90deg, #ff4444, #ff6b6b)';
        } else {
            bar.style.background = 'linear-gradient(90deg, #e94560, #ff6b6b)';
        }
    }
}

// 添加到下载历史
function addToDownloadHistory(item) {
    downloadHistory.unshift(item);
    if (downloadHistory.length > 50) {
        downloadHistory = downloadHistory.slice(0, 50);
    }
    localStorage.setItem('downloadHistory', JSON.stringify(downloadHistory));
    loadDownloadHistory();
}

// 加载下载历史
function loadDownloadHistory() {
    const container = document.getElementById('downloadHistory');
    if (!container) return;
    
    if (downloadHistory.length === 0) {
        container.innerHTML = '<div style="text-align: center; color: #888; padding: 20px;">暂无下载记录</div>';
        return;
    }
    
    container.innerHTML = downloadHistory.map(item => `
        <div style="padding: 12px; margin-bottom: 8px; background: rgba(255,255,255,0.03); border-radius: 10px; display: flex; justify-content: space-between; align-items: center;">
            <div style="flex: 1; min-width: 0;">
                <div style="font-size: 13px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${item.filename}</div>
                <div style="font-size: 11px; color: #888; margin-top: 4px;">
                    ${new Date(item.time).toLocaleString()} · ${formatFileSize(item.size)} · ${getTypeIcon(item.type)}
                </div>
            </div>
            <button onclick="playDownloadedVideo('${item.filename}')" 
                    style="padding: 8px 12px; background: rgba(233,69,96,0.2); color: #e94560; border: none; border-radius: 8px; cursor: pointer; font-size: 12px; margin-left: 10px;">
                ▶️ 播放
            </button>
        </div>
    `).join('');
}

function getTypeIcon(type) {
    const icons = { 'http': '🌐', 'magnet': '🧲', 'telegram': '✈️' };
    return icons[type] || '📁';
}

function formatFileSize(bytes) {
    if (!bytes) return '? B';
    const units = ['B', 'KB', 'MB', 'GB'];
    let i = 0;
    while (bytes >= 1024 && i < units.length - 1) {
        bytes /= 1024;
        i++;
    }
    return bytes.toFixed(1) + ' ' + units[i];
}

function playDownloadedVideo(filename) {
    window.location.href = '/?play=' + encodeURIComponent(filename);
}

// 点击模态框外部关闭
document.addEventListener('click', function(e) {
    const modal = document.getElementById('videoDownloaderModal');
    if (modal && e.target === modal) {
        closeVideoDownloader();
    }
});

// 初始化下载历史
if (downloadHistory.length > 0) {
    // 有历史记录，等待 DOM 加载后显示
    document.addEventListener('DOMContentLoaded', loadDownloadHistory);
}
