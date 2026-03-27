# 多视频上传 UI 增强指南

## 🎨 已完成的更新

### 1. HTML 更新
- ✅ 添加文件列表预览区域 (`fileListPreview`)
- ✅ 添加文件计数器 (`fileCount`)
- ✅ 添加文件摘要 (`fileListSummary`)
- ✅ 添加文件列表 (`fileList`)
- ✅ 添加清空按钮
- ✅ 增强进度条显示（速度、剩余时间、当前文件）

### 2. CSS 样式
- ✅ 文件列表样式
- ✅ 文件项样式（名称、大小、时长）
- ✅ 删除按钮样式
- ✅ 增强进度条动画
- ✅ 统计信息网格
- ✅ 当前文件信息显示
- ✅ 移动端适配
- ✅ 浅色主题适配

### 3. JavaScript 功能
- ✅ `updateFileList()` - 更新文件列表显示
- ✅ `removeFile()` - 移除单个文件
- ✅ `clearAllFiles()` - 清空所有文件
- ✅ `formatDuration()` - 格式化时长
- ✅ 文件去重逻辑
- ✅ 视频时长自动获取
- ✅ 上传速度计算
- ✅ 剩余时间估算

## 📋 需要手动更新的代码

### A. 更新文件选择监听器

在 `static/js/app.js` 中，找到 `DOMContentLoaded` 事件监听器，替换文件选择部分：

```javascript
// 文件选择显示
const fileInput = document.getElementById('file');
const fileInfo = document.getElementById('fileInfo');

if (fileInput) {
    fileInput.addEventListener('change', function(e) {
        const newFiles = e.target.files;
        if (newFiles && newFiles.length > 0) {
            // 合并已选择的文件
            const filesArray = Array.from(newFiles);
            
            // 添加到 selectedFiles（去重）
            filesArray.forEach(newFile => {
                const exists = selectedFiles.some(f => 
                    f.name === newFile.name && f.size === newFile.size
                );
                if (!exists) {
                    selectedFiles.push(newFile);
                }
            });
            
            // 获取视频时长
            let loadedCount = 0;
            selectedFiles.forEach((file, index) => {
                if (file.type.startsWith('video/') && !file.duration) {
                    const video = document.createElement('video');
                    video.src = URL.createObjectURL(file);
                    video.addEventListener('loadedmetadata', function() {
                        file.duration = video.duration;
                        URL.revokeObjectURL(video.src);
                        loadedCount++;
                        if (loadedCount >= selectedFiles.length) {
                            updateFileList(selectedFiles);
                        }
                    });
                }
            });
            
            // 更新列表显示
            updateFileList(selectedFiles);
            
            // 显示汇总信息
            const totalSize = selectedFiles.reduce((sum, f) => sum + f.size, 0);
            const sizeStr = totalSize > 1024 * 1024 * 1024 
                ? `${(totalSize / 1024 / 1024 / 1024).toFixed(2)} GB`
                : `${(totalSize / 1024 / 1024).toFixed(2)} MB`;
            
            if (fileInfo) {
                fileInfo.innerHTML = `
                    <strong style="color: #3b82f6;">📄 已选择 ${selectedFiles.length} 个文件</strong><br>
                    <span style="color: #10b981;">💾 总大小：${sizeStr}</span>
                `;
            }
        }
    });
}
```

### B. 更新 handleUpload 函数

```javascript
function handleUpload(e) {
    e.preventDefault();
    
    const form = e.target;
    const files = selectedFiles.length > 0 ? selectedFiles : fileInput.files;
    const compress = document.getElementById('compressCheck').checked;
    
    if (!files || files.length === 0) {
        showToast('请选择至少一个视频文件', 'error');
        return;
    }
    
    // ... 其余代码保持不变
}
```

### C. 更新上传进度监听

在 `xhr.upload.addEventListener('progress', ...)` 中，更新进度显示：

```javascript
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
            
            // 更新统计信息
            document.getElementById('uploadSize').textContent = `${loadedMB}/${totalMB} MB`;
            document.getElementById('uploadSpeed').textContent = `${speedMBps} MB/s`;
            document.getElementById('uploadETA').textContent = `剩余 ${remainingSeconds}秒`;
            document.getElementById('uploadFileCount').textContent = `${currentFileIndex + 1}/${files.length}`;
        }
    }
});
```

## 🎯 效果预览

### 文件选择后
```
┌─────────────────────────────────────────┐
│ 📋 已选择 5 个文件    [清空全部]        │
├─────────────────────────────────────────┤
│ 💾 总大小：1.2 GB | 📹 视频：5/5 |      │
│ 总时长：25:32                           │
├─────────────────────────────────────────┤
│ 🎬 video1.mp4              [×]          │
│    💾 125 MB  ⏱️ 05:32                 │
├─────────────────────────────────────────┤
│ 🎬 video2.mp4              [×]          │
│    💾 89 MB   ⏱️ 03:45                 │
└─────────────────────────────────────────┘
```

### 上传进度
```
准备上传...                              0%
████████░░░░░░░░░░░░░░░░░░░░░░░░░ 40%

📊 458/1200 MB  |  ⚡ 3.2 MB/s  |  
⏱️ 剩余 230 秒  |  📁 2/5

正在上传：video3.mp4 (256 MB)
```

## ✅ 测试步骤

1. 启动服务器
2. 访问 http://localhost:5001
3. 选择多个视频文件
4. 观察文件列表显示
5. 点击上传查看进度
6. 测试单个文件删除
7. 测试清空全部

## 🎉 完成！
