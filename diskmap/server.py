"""Tiny local web server for the DiskMap UI (standard library only)."""
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

from .disks import other_disks
from .scanner import ScanResult, Scanner, tilde

STATIC = Path(__file__).parent / "static"
PLATFORM = {"win32": "windows", "darwin": "mac"}.get(sys.platform, "linux")


class App:
    def __init__(self, root: str):
        self.root = os.path.realpath(os.path.expanduser(root))
        self.start_root = self.root  # the folder given on the command line
        self.home = os.path.realpath(os.path.expanduser("~"))
        self.disks: list = []
        self.lock = threading.Lock()
        self.scanner: Optional[Scanner] = None
        self.result: Optional[ScanResult] = None
        self.error: Optional[str] = None
        self.scan_id = 0
        self.browser_mode = False  # desktop launcher without a window: the page offers Quit
        self.last_seen = time.time()
        self.bye_at = 0.0  # when a browser-mode tab last said it was closing

    def choices(self) -> list:
        """What the page may ask to scan: the starting folder, home, and other disks."""
        out = []
        for root in dict.fromkeys((self.start_root, self.home)):
            out.append({"root": root, "label": self.label_for(root)})
        out += [d for d in self.disks if d["root"] not in (self.start_root, self.home)]
        return out

    def start_scan(self, root: Optional[str] = None) -> bool:
        with self.lock:
            if self.scanner and self.scanner.running:
                return False
            self.disks = other_disks(self.home)
            if root is not None:
                if root not in {c["root"] for c in self.choices()}:
                    return False
                self.root = root
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

    def label_for(self, root: str) -> str:
        if root == self.home:
            return "~ Home"
        for d in self.disks:
            if d["root"] == root:
                return d["label"]
        return tilde(root, self.home)

    def root_label(self) -> str:
        return self.label_for(self.root)

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
            "browser_mode": self.browser_mode,
            "scan_id": self.scan_id,
            "error": self.error,
            "choices": self.choices(),
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
                "root": r.root,
                "disk": r.disk,
                "scanned": r.tree.size,
                "files": r.files,
                "dirs": r.dirs,
                "errors": r.errors,
                "denied": [tilde(p, self.home) for p in r.denied[:200]],
                "duration": r.duration,
                "finished_at": r.finished_at,
            }
        return out


def make_handler(app: App, port: int):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        server_version = "DiskMap"

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

        def _post_ok(self) -> bool:
            # A custom header forces a CORS preflight (which we never answer), so other
            # websites can't trigger rescans or quit the app from your browser.
            if self.headers.get("X-Diskmap") == "1":
                return True
            self._send(403, b"forbidden", "text/plain")
            return False

        def do_GET(self):
            if not self._host_ok():
                return
            app.last_seen = time.time()
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
            app.last_seen = time.time()
            path = urlparse(self.path).path
            if path == "/api/bye":
                # Sent by navigator.sendBeacon when the tab closes (it can't add headers).
                # Harmless: it only lets browser mode quit sooner if no page is left.
                app.bye_at = time.time()
                self._send(204, b"", "text/plain")
                return
            if not self._post_ok():
                return
            if path == "/api/scan":
                self._json({"started": app.start_scan(self._body().get("root"))})
            elif path == "/api/quit" and app.browser_mode:
                self._json({"ok": True})
                threading.Timer(0.3, os._exit, args=(0,)).start()
            else:
                self._send(404, b"not found", "text/plain")

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return {}
            try:
                data = json.loads(self.rfile.read(min(length, 65536)))
            except ValueError:
                return {}
            return data if isinstance(data, dict) else {}

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
