# -*- mode: python ; coding: utf-8 -*-
import os
import sys

# macOS 双架构：PyInstaller 从 .spec 构建时会忽略命令行的 --target-arch
# （build_main.build() 不接收该参数），所以由这里读环境变量。
# packaging/macos/build.sh 会设置 CC_USAGE_TARGET_ARCH=arm64|x86_64|universal2。
target_arch = os.environ.get("CC_USAGE_TARGET_ARCH") or None
if target_arch and sys.platform != "darwin":
    target_arch = None  # 只有 macOS 才有架构概念


a = Analysis(
    ['cc_usage_reporter/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
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
    name='cc-usage-reporter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=target_arch,
    codesign_identity=None,
    entitlements_file=None,
)