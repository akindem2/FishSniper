# -*- mode: python ; coding: utf-8 -*-
#
# Builds the FishSniper GUI app (entry point: main.py) into a windowed,
# console-less executable.
#
# - The UI is PySide6 (Qt6). PyInstaller's bundled PySide6 hook collects the
#   Qt libraries and plugins automatically, so no manual datas/hiddenimports
#   are needed for it. (Biome thumbnails are QPixmaps fetched over the network
#   at runtime, so nothing image-related needs bundling.)
# - fishing.py imports humancursor for its mouse-path curve generator. The
#   humancursor package __init__ also imports WebCursor, which pulls in
#   selenium (and numpy), so PyInstaller bundles those transitively even
#   though only the curve math is used. That's expected and inflates the
#   build; nothing extra is required for it to work.
# - tkinter / customtkinter are no longer used, so tkinter is excluded to
#   stop Pillow from dragging it into the bundle.

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter'],
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
    icon='icon.ico',
)
