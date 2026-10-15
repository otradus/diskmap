"""Tiny local web server for the diskmap UI (standard library only)."""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from .scanner import ScanResult, Scanner, tilde

STATIC = Path(__file__).parent / "static"
PLATFORM = {"win32": "windows", "darwin": "mac"}.get(sys.platform, "linux")


class App:
    def __init__(self, root: str):
        self.root = os.path.realpath(os.path.expanduser(root))
        self.home = os.path.realpath(os.path.expanduser("~"))
        self.lock = threading.Lock()
        self.scanner: Optional[Scanner] = None
        self.result: Optional[ScanResult] = None
        self.error: Optional[str] = None
        self.scan_id = 0

    def start_scan(self) -> bool:
        with self.lock:
            if self.scanner and self.scanner.running:
                return False
            self.error = None
            self.scanner = Scanner(self.root, self.home)
            scanner = self.scanner
        threading.Thread(target=self._run, args=(scanner,), daemon=True).start()
        return True

    def _run(self, scanner: Scanner) -> None:
        try:
            result = scanner.run()
        except Exception as exc:  # surface it in the UI instead of dying silently
            traceback.print_exc()
            self.error = f"{type(exc).__name__}: {exc}"
            return
        with self.lock:
            self.result = result
            self.scan_id += 1

    def root_label(self) -> str:
        return "~ Home" if self.root == self.home else tilde(self.root, self.home)

    def status(self) -> dict:
        s = self.scanner
        if self.error:
            state = "error"
        elif s and s.running:
            state = "scanning"
        elif self.result:
            state = "done"
        else:
            state = "scanning"
        out = {
            "state": state,
            "root": self.root,
            "root_label": self.root_label(),
            "is_home": self.root == self.home,
            "platform": PLATFORM,
            "scan_id": self.scan_id,
            "error": self.error,
        }
        if s:
            out["progress"] = {
                "files": s.files,
                "dirs": s.dirs,
                "bytes": s.bytes,
                "current": tilde(s.current, self.home),
                "elapsed": time.time() - (s.started or time.time()),
                "waiting": [tilde(p, self.home) for p in s.waiting()] if s.running else [],
            }
        r = self.result
        if r:
            out["summary"] = {
                "disk": r.disk,
                "scanned": r.tree.size,
                "files": r.files,
                "dirs": r.dirs,
                "errors": r.errors,
                "duration": r.duration,
                "finished_at": r.finished_at,
            }
        return out


def make_handler(app: App, port: int):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        server_version = "diskmap"

        def log_message(self, fmt, *args):  # keep the terminal quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data, code: int = 200) -> None:
            self._send(code, json.dumps(data, separators=(",", ":")).encode(), "application/json")

        def _host_ok(self) -> bool:
            # Only answer requests addressed to this machine (blocks DNS-rebinding pages).
            if self.headers.get("Host") in allowed_hosts:
                return True
            self._send(403, b"forbidden", "text/plain")
            return False

        def do_GET(self):
            if not self._host_ok():
                return
            url = urlparse(self.path)
            if url.path in ("/", "/index.html"):
                self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            elif url.path == "/api/status":
                self._json(app.status())
            elif url.path == "/api/recommendations":
                r = app.result
                self._json({"recs": r.recs if r else []})
            elif url.path == "/api/tree":
                self._tree(parse_qs(url.query))
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self):
            if not self._host_ok():
                return
            if urlparse(self.path).path == "/api/scan":
                self._json({"started": app.start_scan()})
            else:
                self._send(404, b"not found", "text/plain")

        def _tree(self, q: dict) -> None:
            r = app.result
            if not r:
                return self._json({"error": "no scan yet"}, 409)
            rel = q.get("path", [""])[0].strip("/")
            depth = max(1, min(4, int(q.get("depth", ["3"])[0])))
            node = r.find(rel)
            if node is None:
                return self._json({"error": f"{rel} is too small to show or doesn't exist"}, 404)
            abspath = os.path.join(r.root, *rel.split("/")) if rel else r.root
            data = r.serialize(node, abspath, depth)
            data["path"] = rel
            self._json(data)

    return Handler


def serve(app: App, port: int) -> tuple:
    last_err = None
    for p in range(port, port + 20):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", p), make_handler(app, p))
            return server, p
        except OSError as exc:
            last_err = exc
    raise SystemExit(f"Couldn't find a free port near {port}: {last_err}")
