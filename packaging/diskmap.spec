# PyInstaller spec for the diskmap app. Build with:  pyinstaller packaging/diskmap.spec
#   macOS   -> dist/diskmap.app
#   Windows -> dist/diskmap.exe
#   Linux   -> dist/diskmap/  (packaging/build_appimage.sh turns it into an AppImage)
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
ICON = os.path.join(SPECPATH, "icon.png")  # PyInstaller converts it to .icns / .ico via Pillow
with open(os.path.join(ROOT, "diskmap", "__init__.py")) as f:
    VERSION = re.search(r'__version__ = "([^"]+)"', f.read()).group(1)
IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"

a = Analysis(
    [os.path.join(SPECPATH, "launch.py")],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, "diskmap", "static"), "diskmap/static")],
    excludes=["tkinter"] + ([] if IS_MAC or IS_WIN else ["webview"]),
)
pyz = PYZ(a.pure)

if IS_WIN:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="diskmap",
              console=False, icon=ICON, upx=False)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="diskmap",
              console=False, icon=ICON if IS_MAC else None, upx=False)
    coll = COLLECT(exe, a.binaries, a.datas, name="diskmap", upx=False)

if IS_MAC:
    why = "diskmap reads folder sizes to show what uses your disk. It never changes files."
    app = BUNDLE(
        coll,
        name="diskmap.app",
        icon=ICON,
        bundle_identifier="io.github.otradus.diskmap",
        version=VERSION,
        info_plist={
            "CFBundleDisplayName": "diskmap",
            "CFBundleShortVersionString": VERSION,
            "LSMinimumSystemVersion": "11.0",
            "NSHighResolutionCapable": True,
            "NSDesktopFolderUsageDescription": why,
            "NSDocumentsFolderUsageDescription": why,
            "NSDownloadsFolderUsageDescription": why,
            "NSRemovableVolumesUsageDescription": why,
            "NSNetworkVolumesUsageDescription": why,
        },
    )
