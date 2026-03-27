#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试磁力链接下载
"""

import subprocess
import os
import time

# 测试磁力链接（Big Buck Bunny 测试种子）
magnet = "magnet:?xt=urn:btih:dd8255ecdc7ca55fb0bbf81323d87062db1f6d1c&dn=Big+Buck+Bunny&tr=udp://explodie.org:6969&tr=udp://tracker.coppersurfer.tk:6969&tr=udp://tracker.empire-js.us:1337&tr=udp://tracker.leechers-paradise.org:6969&tr=udp://tracker.opentrackr.org:1337&tr=udp://tracker.torrent.eu.org:451&tr=udp://tracker.tiny-vps.com:6969&tr=wss://tracker.openwebtorrent.com"

output_dir = "/sdcard/Downloads"
os.makedirs(output_dir, exist_ok=True)

print(f"🧪 测试磁力链接下载")
print(f"磁力：{magnet[:80]}...")
print(f"目录：{output_dir}")
print("")

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
    '--max-tries=5',
    '--continue=true',
    '--enable-dht=true',
    '--enable-dht6=true',
    '--enable-peer-exchange=true',
    '--follow-torrent=true',
    '--listen-port=6881-6999',
    '--console-log-level=warn',
    '--summary-interval=1',
    magnet
]

print("📥 开始下载...")
print(f"命令：aria2c {' '.join(cmd[1:-1])} [磁链]")
print("")

start = time.time()

try:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
    
    elapsed = time.time() - start
    
    print(f"\n完成时间：{elapsed:.1f}秒")
    print(f"返回码：{result.returncode}")
    
    if result.returncode == 0:
        print("✅ 下载成功")
        # 查找下载的文件
        for f in os.listdir(output_dir):
            if 'Big Buck Bunny' in f or f.endswith('.mp4'):
                filepath = os.path.join(output_dir, f)
                size = os.path.getsize(filepath) / 1024 / 1024
                print(f"文件：{filepath} ({size:.1f} MB)")
    else:
        print("❌ 下载失败")
        print(f"错误：{result.stderr[:500]}")
        
except subprocess.TimeoutExpired:
    print("❌ 下载超时（2 小时）")
except Exception as e:
    print(f"❌ 错误：{e}")
