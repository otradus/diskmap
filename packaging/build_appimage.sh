#!/usr/bin/env bash
# Turn the PyInstaller output in dist/diskmap/ into dist/diskmap-linux-x86_64.AppImage.
# Usage: packaging/build_appimage.sh [path/to/appimagetool]   (run after pyinstaller, on Linux)
set -euo pipefail
cd "$(dirname "$0")/.."

TOOL="${1:-appimagetool}"
APPDIR=build/AppDir

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib"
cp -a dist/diskmap "$APPDIR/usr/lib/diskmap"
install -m 755 packaging/appimage/AppRun "$APPDIR/AppRun"
cp packaging/appimage/diskmap.desktop "$APPDIR/diskmap.desktop"
python -c "from PIL import Image; Image.open('packaging/icon.png').resize((256, 256), Image.LANCZOS).save('$APPDIR/diskmap.png')"
ln -sf diskmap.png "$APPDIR/.DirIcon"

# APPIMAGE_EXTRACT_AND_RUN lets appimagetool (itself an AppImage) run without FUSE, e.g. in CI.
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" "$APPDIR" dist/diskmap-linux-x86_64.AppImage
