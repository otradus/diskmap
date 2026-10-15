# diskmap

See what's using your disk, and build a cleanup script for the safe stuff.

- **Explorer**: a treemap of your home folder. Color by *Category* (code projects,
  SDKs, AI models, package caches, documents & media) or by *Cleanup* (safe / needs review).
  Click a tile to drill in; Backspace or Esc goes up.
- **Recommendations**: caches, build output and other regenerable data it found
  (npm/yarn/pnpm, `.next`/`.turbo`, Gradle, Xcode DerivedData, uv/pip, Android SDK,
  Ollama / Hugging Face models, `node_modules` in projects idle 30+ days, Claude
  Code worktrees, and more). Tick items and **Copy script** to get a shell script.

diskmap never deletes anything itself. It only writes a script, and you read it before running it.

Pure Python 3.9+, standard library only. Works on macOS, Linux and Windows:

- **macOS / Linux**: sizes come from allocated blocks; the scan stays on one volume; the script is `sh` (`rm -rf`).
- **Windows**: junctions and mounted folders aren't followed, OneDrive online-only files count as 0,
  `AppData\Local` caches (npm, Yarn, pnpm, pip, uv, Playwright, Android SDK, Docker WSL, Temp) are
  recognised, and the script is PowerShell (`Remove-Item`). Use `py -m diskmap` if `python3` isn't on PATH.
  Very deep `node_modules` paths can exceed Windows' 260-character limit in Windows PowerShell 5.1;
  PowerShell 7 handles them.

## Run

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

## How it works

- `diskmap/scanner.py`: a multi-threaded `os.scandir` walk. Sizes are allocated blocks
  (what's really on disk), hard links count once, and the scan stays on one volume. Entries
  under 1 MB are merged into "N smaller items" so memory stays bounded.
- `diskmap/rules.py`: category mapping and cleanup rules. Add a `Rule(...)` to teach it a
  new cache (by home-relative path, or by folder name inside your projects).
- `diskmap/server.py`: a small `http.server` JSON API that serves only 127.0.0.1.
- `diskmap/static/index.html`: the UI (vanilla JS, squarified treemap).
