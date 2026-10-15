"""DiskMap as a desktop app: its own window on macOS and Windows, the browser on Linux.

    python -m diskmap.desktop

DISKMAP_ROOT=<folder> scans another folder; DISKMAP_BROWSER=1 forces browser mode.
"""
from __future__ import annotations

import os
import stat
import sys
import threading
import time
import webbrowser

from .server import App, serve

# Browser mode has no window to close, so it quits once no page has been open for a while.
# Background tabs may only run timers once a minute, hence the generous idle limit.
IDLE_QUIT_SECONDS = 180
FIRST_LOAD_SECONDS = 120   # time allowed for the browser to open the page at all
BYE_QUIT_SECONDS = 8       # after the tab says goodbye, quit unless a page comes back (reload)


class DesktopApi:
    """Methods the page can call as window.pywebview.api.*"""

    def __init__(self):
        self._window = None

    def copy(self, text: str) -> bool:
        """Copy via pbcopy on macOS, where WKWebView may refuse clipboard writes."""
        if sys.platform != "darwin":
            return False  # WebView2 on Windows handles navigator.clipboard itself
        import subprocess

        return subprocess.run(["pbcopy"], input=text.encode("utf-8")).returncode == 0

    def save_script(self, text: str, filename: str):
        import webview

        dialog = webview.FileDialog.SAVE if hasattr(webview, "FileDialog") else webview.SAVE_DIALOG
        result = self._window.create_file_dialog(dialog, save_filename=filename)
        if not result:
            return None
        path = result if isinstance(result, str) else result[0]
        with open(path, "w", newline="", encoding="utf-8") as f:
            f.write(text)
        if os.name != "nt":
            os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return path


def run_in_window(webview, server, url: str) -> None:
    threading.Thread(target=server.serve_forever, daemon=True).start()
    api = DesktopApi()
    window = webview.create_window("DiskMap", url, js_api=api, width=1360, height=880, min_size=(900, 600))
    api._window = window
    webview.start()
    server.shutdown()


def run_in_browser(app: App, server, url: str) -> None:
    app.browser_mode = True
    started = time.time()

    def watchdog():
        while True:
            time.sleep(2)
            now = time.time()
            if app.bye_at and app.last_seen <= app.bye_at and now - app.bye_at > BYE_QUIT_SECONDS:
                os._exit(0)
            never_loaded = app.last_seen < started
            if now - app.last_seen > (FIRST_LOAD_SECONDS if never_loaded else IDLE_QUIT_SECONDS):
                os._exit(0)

    threading.Thread(target=watchdog, daemon=True).start()
    print(f"DiskMap is running at {url}  (use Quit in the page, or close the tab)")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


def main() -> None:
    app = App(os.environ.get("DISKMAP_ROOT", "~"))
    server, port = serve(app, 8765)
    url = f"http://127.0.0.1:{port}/"
    app.start_scan()

    webview = None
    if sys.platform != "linux" and not os.environ.get("DISKMAP_BROWSER"):
        try:
            import webview
        except ImportError:
            webview = None

    if webview is None:
        run_in_browser(app, server, url)
    else:
        run_in_window(webview, server, url)
    # Scan worker threads aren't daemons; don't wait for a scan in progress.
    os._exit(0)


if __name__ == "__main__":
    main()
