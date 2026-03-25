"""
验证修复：用 HikvisionISAPI 类（Digest Auth）连接 10.26.223.253
"""
import sys
sys.path.insert(0, r'c:\Users\Administrator\WorkBuddy\20260323192840\hikvision_downloader')

from core.nvr_api import HikvisionISAPI

HOST = "10.26.223.253"
PORT = 80
USER = "admin"
PASS = "a1111111"

print(f"连接 {HOST}:{PORT}...")
api = HikvisionISAPI(HOST, PORT, USER, PASS)

# 测试连接
ok, model = api.test_connection()
print(f"连接测试: ok={ok}  model={model}")

# 获取通道列表（含在线状态）
print("\n获取通道信息（含OSD名称和在线状态）...")
channels = api._get_channels_from_input_proxy()
print(f"获取到 {len(channels)} 个通道")

online  = sum(1 for c in channels.values() if c['online'])
offline = len(channels) - online
print(f"在线: {online}  离线/未知: {offline}")

if channels:
    print("\n前10个通道:")
    for no in sorted(channels.keys())[:10]:
        c = channels[no]
        status = "✅在线" if c['online'] else "❌离线"
        print(f"  通道{no:3d}: {c['name']:30s}  {status}  ({c['status']})")
else:
    print("未获取到通道信息！")
    # 备用：Streaming/channels
    print("\n尝试 Streaming/channels...")
    names = api._get_names_from_streaming()
    print(f"Streaming 获取到 {len(names)} 个通道名")
    for no in sorted(names.keys())[:10]:
        print(f"  通道{no:3d}: {names[no]}")
