# -*- mode: python ; coding: utf-8 -*-
import customtkinter
import os

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[(customtkinter.__path__[0], 'customtkinter/')],
    hiddenimports=[
        'aiohttp',
        'customtkinter',
        'discord.py-self',
        'pyautogui',
        'requests',
        'rich',
        'PIL',
        'win32api',
        'win32con',
        'win32gui',
        'keyboard',
        'curl_cffi',
        'google.protobuf',
        'packaging',
        'tzlocal',
        'tzdata',
        'audioop',
        'cffi',
        'markdown_it',
        'propcache'
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
