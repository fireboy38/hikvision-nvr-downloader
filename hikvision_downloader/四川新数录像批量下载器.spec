# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=['PyQt5', 'PyQt5.sip', 'requests', 'urllib3', 'xml.etree.ElementTree', 'xml.etree.cElementTree', 'json', 'datetime', 'os', 'sys', 'subprocess', 'threading', 'time', 're', 'pathlib', 'typing', 'dataclasses', 'gui', 'gui.main_window', 'core', 'core.downloader', 'core.java_downloader', 'core.nvr_api', 'core.hcnetsdk', 'core.channel_manager', 'core.device_info', 'core.hikload_downloader', 'core.isapi_downloader', 'core.osd_manager', 'utils', 'utils.logger'],
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
    name='四川新数录像批量下载器',
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
