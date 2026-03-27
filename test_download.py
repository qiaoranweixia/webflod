#!/usr/bin/env python
import subprocess
import os
import time

# 用户提供的磁力链接
magnet = "magnet:?xt=urn:btih:d43776d4eaa7396987c2d5ce1782e21f9dd30965"

# 输出目录
output_dir = "/data/data/com.termux/files/home/video_site_project/uploads"
os.makedirs(output_dir, exist_ok=True)

print("="*60)
print("🧪 测试磁力链接下载")
print("="*60)
print(f"磁力：{magnet}")
print(f"目录：{output_dir}")
print("")

# 公共 tracker 列表
trackers = [
    'udp://tracker.openbittorrent.com:80',
    'udp://tracker.opentrackr.org:1337',
    'udp://tracker.coppersurfer.tk:6969',
    'udp://tracker.dler.org:6969',
    'udp://open.stealth.si:80',
    'udp://tracker.torrent.eu.org:451',
    'udp://tracker.moeking.me:6969',
    'udp://exodus.desync.com:6969',
    'udp://tracker.internetwarriors.net:1337',
    'wss://tracker.openwebtorrent.com',
    'wss://tracker.btorrent.xyz',
]

# aria2c 命令
cmd = [
    'aria2c',
    '--dir=' + output_dir,
    '--seed-time=0',
    '--max-connection-per-server=16',
    '--split=16',
    '--min-split-size=1M',
    '--connect-timeout=600',
    '--timeout=600',
    '--retry-wait=5',
    '--max-tries=20',
    '--continue=true',
    '--user-agent=Mozilla/5.0',
    '--enable-dht=true',
    '--enable-dht6=true',
    '--enable-peer-exchange=true',
    '--follow-torrent=true',
    '--listen-port=6881-6999',
    '--bt-tracker=' + ','.join(trackers),
    '--bt-request-peer-speed-limit=10M',
    '--bt-max-peers=100',
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
    result = subprocess.run(cmd, timeout=1800)  # 30 分钟超时
    
    elapsed = time.time() - start
    
    print(f"\n⏱️  耗时：{elapsed:.1f}秒")
    print(f"返回码：{result.returncode}")
    
    if result.returncode == 0:
        print("✅ 下载成功")
        # 查找下载的文件
        for f in os.listdir(output_dir):
            filepath = os.path.join(output_dir, f)
            if os.path.isfile(filepath):
                size = os.path.getsize(filepath) / 1024 / 1024
                print(f"📁 文件：{filepath} ({size:.1f} MB)")
    else:
        print("❌ 下载失败")
        
except subprocess.TimeoutExpired:
    print("❌ 下载超时（30 分钟）")
except Exception as e:
    print(f"❌ 错误：{e}")

