# DiskMap

See what's using your disk, and build a cleanup script for the safe stuff.

- **Explorer**: a treemap of your home folder. Color by *Category* (code projects,
  SDKs, AI models, package caches, documents & media) or by *Cleanup* (safe / needs review).
  Click a tile to drill in; Backspace or Esc goes up. If you have more than one disk,
  pick it from the menu at the top. Hover "N folders unreadable" to see which ones.
  The theme follows your system, or pick Light or Dark in the top bar.
- **Recommendations**: caches, build output and other regenerable data it found
  (npm/yarn/pnpm, `.next`/`.turbo`, Gradle, Xcode DerivedData, uv/pip, Android SDK,
  Ollama / Hugging Face models, `node_modules` in projects idle 30+ days, Claude
  Code worktrees, and more). Tick items and **Copy script** to get a shell script.

DiskMap never deletes anything itself. It only writes a script, and you read it before running it.

Pure Python 3.9+, standard library only. Works on macOS, Linux and Windows:

- **macOS / Linux**: sizes come from allocated blocks; the scan stays on one volume; the script is `sh` (`rm -rf`).
- **Windows**: junctions and mounted folders aren't followed, OneDrive online-only files count as 0,
  `AppData\Local` caches (npm, Yarn, pnpm, pip, uv, Playwright, Android SDK, Docker WSL, Temp) are
  recognised, and the script is PowerShell (`Remove-Item`). Use `py -m diskmap` if `python3` isn't on PATH.
  Very deep `node_modules` paths can exceed Windows' 260-character limit in Windows PowerShell 5.1;
  PowerShell 7 handles them.

## Download the app

Get the latest build from [Releases](https://github.com/otradus/diskmap/releases). No Python needed.

| Platform | File | Opens in |
|---|---|---|
| macOS (Apple Silicon) | `diskmap-macos-arm64.zip` → `DiskMap.app` | its own window |
| Windows 10/11 | `diskmap-windows-x64.exe` | its own window |
| Linux (x86_64) | `diskmap-linux-x86_64.AppImage` | your browser |

The builds aren't code-signed, so the first launch needs one extra step:

- **macOS**: if it says Apple could not verify DiskMap, open System Settings → Privacy & Security
  and click **Open Anyway**. To scan protected folders without prompts, give **DiskMap** itself
  Full Disk Access. You may need to grant that again after installing a new version.
- **Windows**: on "Windows protected your PC", click **More info → Run anyway**.
- **Linux**: `chmod +x diskmap-linux-x86_64.AppImage` and run it. It opens in your browser. Use
  **Quit** in the page, or just close the tab: it stops by itself (within a few minutes at most).
  If it complains about FUSE, install your distro's FUSE package or run it with
  `--appimage-extract-and-run`.

## Run from source

```bash
python3 -m diskmap
```

That scans `~` and opens http://127.0.0.1:8765. Other options:

```bash
python3 -m diskmap ~/Projects      # scan one folder
python3 -m diskmap --report        # text report in the terminal, no UI
python3 -m diskmap --no-browser --port 9000
pip install -e . && diskmap        # install as a command
```

On macOS, the first scan may trigger "Terminal would like to access files in your
Desktop/Documents folder" prompts. Folders you deny show up as "no access". To let it
see everything, give your terminal Full Disk Access in System Settings → Privacy & Security.

## Build the app yourself

```bash
python3 -m venv .venv && .venv/bin/pip install -r packaging/requirements.txt
.venv/bin/pyinstaller packaging/diskmap.spec    # → dist/DiskMap.app, dist/diskmap.exe or dist/diskmap/
```

Build on the platform you're targeting (PyInstaller can't cross-compile). On Linux, run
`packaging/build_appimage.sh path/to/appimagetool` afterwards to get the AppImage.
`.venv/bin/python -m diskmap.desktop` runs the app version from source.
Pushing a `v*` tag runs `.github/workflows/release.yml`, which builds all three and publishes a Release.

## How it works

- `diskmap/scanner.py`: a multi-threaded `os.scandir` walk. Sizes are allocated blocks
  (what's really on disk), hard links count once, and the scan stays on one volume. Entries
  under 1 MB are merged into "N smaller items" so memory stays bounded.
- `diskmap/rules.py`: category mapping and cleanup rules. Add a `Rule(...)` to teach it a
  new cache (by home-relative path, or by folder name inside your projects).
- `diskmap/disks.py`: finds the other mounted disks you can pick in the UI.
- `diskmap/server.py`: a small `http.server` JSON API that serves only 127.0.0.1.
- `diskmap/static/index.html`: the UI (vanilla JS, squarified treemap).
- `diskmap/desktop.py`: the app launcher. Uses a pywebview window on macOS/Windows, and the
  browser (with Quit and auto-exit) on Linux.
- `packaging/`: PyInstaller spec, icon, and AppImage files.
