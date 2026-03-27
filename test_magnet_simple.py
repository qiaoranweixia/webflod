#!/usr/bin/env python
import subprocess
import os
import time

# 测试磁力链接
magnet = "magnet:?xt=urn:btih:dd8255ecdc7ca55fb0bbf81323d87062db1f6d1c&dn=Big+Buck+Bunny&tr=udp://tracker.openbittorrent.com:80"

output_dir = "/sdcard/Downloads"
os.makedirs(output_dir, exist_ok=True)

print("🧪 测试磁力链接下载")
print(f"输出目录：{output_dir}")
print("")

# 简化的 aria2c 命令
cmd = [
    'aria2c',
    '--dir=' + output_dir,
    '--seed-time=0',
    '--max-connection-per-server=16',
    '--split=16',
    '--connect-timeout=600',
    '--timeout=600',
    '--max-tries=20',
    '--continue=true',
    '--enable-dht=true',
    '--enable-peer-exchange=true',
    '--follow-torrent=true',
    '--console-log-level=notice',
    '--summary-interval=1',
    magnet
]

print("📥 开始下载...")
print(f"命令：aria2c {' '.join(cmd[1:-1])} [磁链]")
print("")

start = time.time()

try:
    # 直接运行，显示输出
    result = subprocess.run(cmd, timeout=7200)
    
    elapsed = time.time() - start
    
    print(f"\n⏱️  耗时：{elapsed:.1f}秒")
    print(f"返回码：{result.returncode}")
    
    if result.returncode == 0:
        print("✅ 下载成功")
        # 查找文件
        for f in os.listdir(output_dir):
            if 'mp4' in f.lower() or 'mkv' in f.lower():
                filepath = os.path.join(output_dir, f)
                size = os.path.getsize(filepath) / 1024 / 1024
                print(f"📁 文件：{filepath} ({size:.1f} MB)")
    else:
        print("❌ 下载失败")
        
except subprocess.TimeoutExpired:
    print("❌ 下载超时（2 小时）")
except Exception as e:
    print(f"❌ 错误：{e}")

