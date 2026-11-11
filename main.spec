# -*- mode: python ; coding: utf-8 -*-
#
# 只产出目录版: dist/S参数串扰计算_dir/
# (单文件版每次启动需向 %TEMP%\_MEI* 解包并被杀软扫描, 实测 8-9s 且偶发
#  120s 级尖峰; 目录版启动 1-2s, 故弃用 onefile)

import json
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

# PyInstaller 6.22 无 hook-ttkbootstrap, 主题图标字体 (bootstrap.ttf)
# 不会自动收集, 必须显式声明, 否则启动即 FileNotFoundError
datas = collect_data_files('ttkbootstrap')
branding_path = Path(SPECPATH) / 'branding.private.json'
if branding_path.exists():
    try:
        branding = json.loads(branding_path.read_text(encoding='utf-8-sig'))
        author = branding.get('author') if isinstance(branding, dict) else None
        if not isinstance(author, str) or not author.strip():
            raise ValueError
    except (OSError, ValueError):
        raise SystemExit('branding.private.json 必须包含非空字符串 author') from None
    datas.append((str(branding_path), '.'))

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 运行时依赖 scipy (PCHIP 插值), 不能排除;
        # 只排除与运行时无关的测试/构建包
        'numpy.tests', 'numpy.distutils', 'matplotlib.tests',
        'tkinter.test', 'tkinter.tix',
        'pip', 'setuptools', 'distutils',
    ],
    noarchive=False,
    optimize=0,
)
# plot_runtime isolates configuration while retaining a persistent font cache.
a.scripts = [script for script in a.scripts if script[0] != 'pyi_rth_mplconfig']
pyz = PYZ(a.pure)


# ---- onedir: dist/S参数串扰计算_dir/S参数串扰计算.exe ----
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='S参数串扰计算',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='S参数串扰计算_dir',
)
