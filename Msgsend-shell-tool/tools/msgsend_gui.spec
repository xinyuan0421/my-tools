# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for msgsend_gui — single-file Windows EXE
# Build on Windows:  pyinstaller msgsend_gui.spec

block_cipher = None

a = Analysis(
    ['msgsend_gui.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['tkinter', 'tkinter.ttk', 'tkinter.filedialog', 'tkinter.messagebox'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['numpy', 'pandas', 'matplotlib', 'scipy'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='msgsend_gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # no black console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,              # replace with 'icon.ico' if you have one
)
