# -*- mode: python ; coding: utf-8 -*-
"""FluxPack PyInstaller spec — 单文件 GUI EXE"""

a = Analysis(
    ['run_launcher.py'],
    pathex=['D:\\FluxPack'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'customtkinter',
        'py7zr',
        'pyzipper',
        'rarfile',
        'PIL',
        'PIL._tkinter_finder',
        'piexif',
        'click',
        'rich',
        'rich.progress',
        'rich.table',
        'rich.panel',
        'rich.layout',
        'winreg',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter.test',
        'unittest',
        'pytest',
        'numpy',
        'matplotlib',
        'scipy',
        'notebook',
        'jupyter',
        'uvicorn',
        'fastapi',
        'jinja2',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.protocols',
    ],
    noarchive=False,
    optimize=1,  # 适度优化
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='FluxPack',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,      # 双模式：无参数→GUI，有参数→CLI
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
