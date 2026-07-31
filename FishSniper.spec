# -*- mode: python ; coding: utf-8 -*-
#
# Builds the FishSniper GUI app (entry point: main.py) into a windowed,
# console-less executable.
#
# - CustomTkinter ships its own PyInstaller hook, which bundles its
#   theme/asset files automatically — no manual `datas` entries needed.
# - `PIL._tkinter_finder` is listed explicitly in hiddenimports: it's a
#   dynamic import that PyInstaller can miss, and is needed here because
#   the UI's biome thumbnails go through CustomTkinter's CTkImage, which
#   relies on Pillow's ImageTk integration.

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['PIL._tkinter_finder'],
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
    name='FishSniper',
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
