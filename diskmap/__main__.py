"""DiskMap: see what's using your disk and build a cleanup script.

    python -m diskmap                 # scan your home folder and open the UI
    python -m diskmap ~/Projects      # scan a specific folder
    python -m diskmap --report        # print a text report, no browser
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import webbrowser

from .scanner import Scanner, tilde
from .server import App, serve


def fmt(n: float) -> str:
    for unit, div in (("TB", 1e12), ("GB", 1e9), ("MB", 1e6), ("KB", 1e3)):
        if n >= div:
            return f"{n / div:.1f} {unit}"
    return f"{int(n)} B"


def report(root: str) -> None:
    scanner = Scanner(root)
    done = threading.Event()

    def progress():
        while not done.wait(0.25):
            sys.stderr.write(f"\r  scanning… {scanner.files:,} files · {fmt(scanner.bytes)}   ")
            sys.stderr.flush()

    threading.Thread(target=progress, daemon=True).start()
    result = scanner.run()
    done.set()
    sys.stderr.write("\r" + " " * 60 + "\r")

    home = scanner.home
    print(f"\n{tilde(result.root, home)}  {fmt(result.tree.size)}  "
          f"({result.files:,} files, {result.duration:.1f}s, {result.errors} unreadable folders)")
    d = result.disk
    print(f"Disk: {fmt(d['free'])} free of {fmt(d['total'])}\n")

    print("Largest items")
    for c in [c for c in result.tree.children or [] if not c.agg][:15]:
        print(f"  {fmt(c.size):>10}  {c.name}{'/' if c.is_dir else ''}")

    for safety, label in (("safe", "Safe to remove"), ("review", "Review first")):
        recs = [r for r in result.recs if r["safety"] == safety]
        if not recs:
            continue
        print(f"\n{label} — {fmt(sum(r['size'] for r in recs))}")
        for r in recs:
            print(f"  {fmt(r['size']):>10}  {r['title']}  ({r['where']})")
    print()


def main() -> None:
    ap = argparse.ArgumentParser(prog="diskmap", description="Disk usage explorer and cleanup helper.")
    ap.add_argument("root", nargs="?", default="~", help="folder to scan (default: your home folder)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true", help="don't open a browser window")
    ap.add_argument("--report", action="store_true", help="print a text report and exit")
    args = ap.parse_args()

    root = os.path.realpath(os.path.expanduser(args.root))
    if not os.path.isdir(root):
        ap.error(f"not a folder: {args.root}")

    if args.report:
        report(root)
        return

    app = App(root)
    server, port = serve(app, args.port)
    app.start_scan()
    url = f"http://127.0.0.1:{port}/"
    print(f"DiskMap is scanning {tilde(root, app.home)}")
    print(f"Open {url}  (Ctrl+C to quit)")
    if not args.no_browser:
        threading.Timer(0.3, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
