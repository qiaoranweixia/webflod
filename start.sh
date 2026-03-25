#!/bin/bash
# Flask 视频网站启动脚本

echo "🎬 正在启动视频中心..."
echo ""

# 检查 Python
if ! command -v python &> /dev/null; then
    echo "❌ 错误：未找到 Python"
    exit 1
fi

# 检查依赖
if ! python -c "import flask" 2>/dev/null; then
    echo "⚠️  正在安装依赖..."
    pip install -r requirements.txt
fi

# 创建上传目录
mkdir -p uploads

# 获取本机 IP
IP=$(hostname -I | awk '{print $1}')

echo "✅ 服务已启动！"
echo ""
echo "📱 本地访问：http://localhost:5001"
echo "🌐 局域网访问：http://$IP:5001"
echo ""
echo "按 Ctrl+C 停止服务"
echo ""

# 启动应用
python app.py
