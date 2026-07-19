# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("static", "static"),
        ("templates", "templates"),
        ("VERSION", "."),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "IPython",
        "matplotlib",
        "numpy",
        "pandas",
        "pygame",
        "pytest",
        "scipy",
        "tensorflow",
        "torch",
    ],
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
    name="PDFeditorAthome",
    icon="packaging/assets/pdf-editor-at-home.ico",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version="packaging/windows-version-info.txt",
)
