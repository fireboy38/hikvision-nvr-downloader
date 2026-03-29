# -*- mode: python ; coding: utf-8 -*-
# 带DLL的打包配置 - 目录模式（更稳定）

import os
import sys

# 获取脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(SPEC))

# SDK路径 - 优先使用V6.1.11.5，找不到则用V6.1.6.45
SDK_PATHS = [
    r"C:\Users\Administrator\Downloads\HCNetSDKV6.1.11.5_build20251204_Win64_ZH_20260320151956\CH-HCNetSDKV6.1.11.5_build20251204_Win64_ZH\库文件",
    r"C:\Users\Administrator\Downloads\HCNetSDKV6.1.11.5_build20251204_Win64_ZH_20260320151956\HCNetSDKV6.1.11.5_build20251204_Win64_ZH\库文件",
    r"C:\Users\Administrator\CH-HCNetSDKV6.1.6.45_build20210302_win64_20210508181836\CH-HCNetSDKV6.1.6.45_build20210302_win64\库文件",
]

SDK_PATH = None
for path in SDK_PATHS:
    if os.path.exists(path):
        SDK_PATH = path
        print(f"使用SDK路径: {SDK_PATH}")
        break

if SDK_PATH is None:
    print("错误: 未找到海康SDK库文件目录!")
    sys.exit(1)

# 主DLL文件列表
main_dlls = [
    "HCNetSDK.dll",
    "HCCore.dll",
    "hpr.dll",
    "PlayCtrl.dll",
    "SuperRender.dll",
    "AudioRender.dll",
    "GdiPlus.dll",
    # V6.1.11.5额外DLL
    "AudioProcess.dll",
    "hlog.dll",
    "HmMerge.dll",
    "HXVA.dll",
    "libcrypto-3-x64.dll",
    "libmmd.dll",
    "libssl-3-x64.dll",
    "MP_Render.dll",
    "NPQos.dll",
    "OpenAL32.dll",
    "YUVProcess.dll",
    "zlib1.dll",
    # V6.1.6.x兼容DLL
    "libcrypto-1_1-x64.dll",
    "libssl-1_1-x64.dll",
    "StreamTransClient.dll",
]

# 收集所有DLL文件
binaries = []
for dll in main_dlls:
    dll_path = os.path.join(SDK_PATH, dll)
    if os.path.exists(dll_path):
        binaries.append((dll_path, "."))
        print(f"添加主DLL: {dll}")

# 添加HCNetSDKCom目录下的所有DLL
hcnet_sdk_com = os.path.join(SDK_PATH, "HCNetSDKCom")
if os.path.exists(hcnet_sdk_com):
    for f in os.listdir(hcnet_sdk_com):
        if f.endswith(".dll"):
            dll_path = os.path.join(hcnet_sdk_com, f)
            binaries.append((dll_path, "HCNetSDKCom"))
            print(f"添加HCNetSDKCom: {f}")

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=binaries,
    datas=[],
    hiddenimports=[
        'PyQt5', 'PyQt5.sip', 'requests', 'urllib3',
        'xml.etree.ElementTree', 'xml.etree.cElementTree',
        'json', 'datetime', 'os', 'sys', 'subprocess',
        'threading', 'time', 're', 'pathlib', 'typing', 'dataclasses',
        'gui', 'gui.main_window',
        'core', 'core.downloader', 'core.java_downloader', 'core.nvr_api',
        'core.hcnetsdk', 'core.channel_manager', 'core.device_info',
        'core.hikload_downloader', 'core.isapi_downloader', 'core.osd_manager',
        'utils', 'utils.logger'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],  # 目录模式：binaries和datas移到COLLECT
    exclude_binaries=True,  # 目录模式
    name='四川新数录像批量下载器',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# 目录模式：收集所有文件到一个文件夹
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='四川新数录像批量下载器',
)
