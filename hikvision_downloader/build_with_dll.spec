# -*- mode: python ; coding: utf-8 -*-
# 带DLL的打包配置 - 生成单文件exe

import os

# SDK路径
SDK_PATH = r"C:\Users\Administrator\CH-HCNetSDKV6.1.6.45_build20210302_win64_20210508181836\CH-HCNetSDKV6.1.6.45_build20210302_win64\库文件"

# 主DLL文件列表
main_dlls = [
    "HCNetSDK.dll",
    "HCCore.dll", 
    "hpr.dll",
    "PlayCtrl.dll",
    "StreamTransClient.dll",
    "SuperRender.dll",
    "AudioRender.dll",
    "GdiPlus.dll",
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

# Java组件（可选，程序实际不需要jar）
# datas = []
# jna_jar = r"c:\Users\Administrator\WorkBuddy\20260323192840\hikvision_java\src\main\resources\lib\jna.jar"
# if os.path.exists(jna_jar):
#     datas.append((jna_jar, "lib"))

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
    a.binaries,
    a.datas,
    [],
    name='四川新数录像批量下载器_完整版',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
