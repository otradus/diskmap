"""Walks a folder, builds a size tree and collects cleanup candidates."""
from __future__ import annotations

import os
import shutil
import stat
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from . import rules

KEEP_MIN_BYTES = 1_000_000   # smaller entries are folded into one "N smaller items" tile
KEEP_MAX_CHILDREN = 150      # per directory, largest first
MIN_REC_BYTES = 1_000_000    # ignore cleanup candidates smaller than this
WORKERS = min(32, (os.cpu_count() or 4) * 2)

IS_WINDOWS = os.name == "nt"
# Junctions, mounted volumes and directory symlinks: don't follow (loops, other drives).
_SKIP_REPARSE_TAGS = {
    getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003),
    getattr(stat, "IO_REPARSE_TAG_SYMLINK", 0xA000000C),
}
# FILE_ATTRIBUTE_OFFLINE | RECALL_ON_OPEN | RECALL_ON_DATA_ACCESS: OneDrive "online-only" files.
_CLOUD_ONLY_ATTRS = 0x1000 | 0x40000 | 0x400000


class Node:
    __slots__ = ("name", "size", "is_dir", "cat", "children", "mtime", "agg", "count", "denied")

    def __init__(self, name: str, is_dir: bool, size: int = 0, cat: str = "other"):
        self.name = name
        self.is_dir = is_dir
        self.size = size
        self.cat = cat
        self.children: Optional[list] = None
        self.mtime = 0.0      # newest file change in this subtree (ignoring QUIET_DIRS)
        self.agg = False      # True for the "N smaller items" placeholder
        self.count = 0
        self.denied = False   # couldn't list this directory

    def child(self, name: str) -> Optional["Node"]:
        for c in self.children or ():
            if c.name == name and not c.agg:
                return c
        return None


class Found:
    __slots__ = ("rule", "path", "node", "project")

    def __init__(self, rule, path, node, project):
        self.rule, self.path, self.node, self.project = rule, path, node, project


def _disk_bytes(st: os.stat_result) -> int:
    # Allocated blocks, not apparent size: sparse files and cloud placeholders count as what they use.
    blocks = getattr(st, "st_blocks", None)
    if blocks is not None:
        return blocks * 512
    if getattr(st, "st_file_attributes", 0) & _CLOUD_ONLY_ATTRS:  # Windows has no st_blocks
        return 0
    return st.st_size


class Scanner:
    def __init__(self, root: str, home: Optional[str] = None):
        self.root = os.path.realpath(os.path.expanduser(root))
        self.home = os.path.realpath(home or os.path.expanduser("~"))
        if self.root == self.home:
            self.root_rel: Optional[str] = ""
        elif self.root.startswith(self.home + os.sep):
            self.root_rel = os.path.relpath(self.root, self.home).replace(os.sep, "/")
        else:
            self.root_rel = None  # outside home: path-based rules don't apply
        self.files = self.dirs = self.bytes = self.errors = 0
        self.current = self.root
        self.started: Optional[float] = None
        self.finished: Optional[float] = None
        self.found: list = []
        self.denied: list = []  # folders we couldn't list
        self._lock = threading.Lock()
        self._inodes: set = set()
        self._opening: dict = {}  # thread id -> (path, since); spots listings stuck on a macOS privacy prompt
        self._dev = os.stat(self.root).st_dev
        self._outer = self._inner = None

    @property
    def running(self) -> bool:
        return self.started is not None and self.finished is None

    def run(self) -> "ScanResult":
        self.started = time.time()
        try:
            # Top-level folders scan in parallel, and each of them fans its own
            # subfolders out to a second pool. Only the outer pool waits on the inner
            # one, so they can't deadlock.
            with ThreadPoolExecutor(4) as outer, ThreadPoolExecutor(WORKERS) as inner:
                self._outer, self._inner = outer, inner
                name = os.path.basename(self.root) or self.root
                tree = self._scan(self.root, name, self.root_rel, None, False, 0)
        finally:
            self.finished = time.time()
        return ScanResult(self, tree)

    def waiting(self, min_seconds: float = 2.0) -> list:
        """Folders whose listing has been blocked for a while (usually a permission dialog)."""
        now = time.time()
        return sorted(p for p, since in list(self._opening.values()) if now - since >= min_seconds)

    def rel_of(self, path: str) -> str:
        rel = os.path.relpath(path, self.root)
        return "" if rel == "." else rel.replace(os.sep, "/")

    def _scan(self, path: str, name: str, rel: Optional[str], inherited: Optional[str],
              in_found: bool, depth: int) -> Node:
        node = Node(name, True)
        own = (rules.PATH_CATEGORIES.get(rel) if rel is not None else None) or inherited
        tid = threading.get_ident()
        self._opening[tid] = (path, time.time())
        try:
            with os.scandir(path) as it:
                entries = list(it)
        except OSError:
            self._opening.pop(tid, None)
            node.denied = True
            node.cat = own or "other"
            with self._lock:
                self.errors += 1
                self.denied.append(path)
            return node
        self._opening.pop(tid, None)

        names = {e.name for e in entries}
        if own is None and depth > 0 and not names.isdisjoint(rules.PROJECT_MARKERS):
            own = "code"

        cat_sizes: dict = defaultdict(int)
        kids = []
        subdirs = []
        nfiles = nbytes = 0
        mtime = 0.0
        for e in entries:
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            mode = st.st_mode
            if stat.S_ISDIR(mode):
                if IS_WINDOWS:
                    # DirEntry.stat() reports st_dev as 0 on Windows; other volumes are
                    # reached through junctions / mount points, so skip those instead.
                    if getattr(st, "st_reparse_tag", 0) in _SKIP_REPARSE_TAGS:
                        continue
                elif st.st_dev != self._dev:  # don't wander onto other volumes
                    continue
                subdirs.append(e)
                continue
            if not stat.S_ISREG(mode):
                continue
            if st.st_nlink > 1:  # count hard-linked files once (pnpm, Time Machine…)
                key = (st.st_dev, st.st_ino)
                with self._lock:
                    if key in self._inodes:
                        continue
                    self._inodes.add(key)
            size = _disk_bytes(st)
            nfiles += 1
            nbytes += size
            if st.st_mtime > mtime:
                mtime = st.st_mtime
            fcat = own or rules.file_category(e.name)
            cat_sizes[fcat] += size
            if size >= KEEP_MIN_BYTES:
                kids.append(Node(e.name, False, size, fcat))
        node.size = nbytes
        with self._lock:
            self.files += nfiles
            self.bytes += nbytes
            self.dirs += 1
            self.current = path

        jobs = []
        for e in subdirs:
            child_rel = None if rel is None else (f"{rel}/{e.name}" if rel else e.name)
            rule = None if in_found else rules.match_dir(e.name, child_rel, name, names, e.path)
            jobs.append((e, child_rel, rule))

        def scan_child(job):
            e, child_rel, rule = job
            return self._scan(e.path, e.name, child_rel, own, in_found or rule is not None, depth + 1)

        if depth == 0:
            results = list(self._outer.map(scan_child, jobs))
        elif depth == 1:
            results = list(self._inner.map(scan_child, jobs))
        else:
            results = [scan_child(j) for j in jobs]

        for (e, _rel, rule), child in zip(jobs, results):
            node.size += child.size
            cat_sizes[child.cat] += child.size
            if e.name not in rules.QUIET_DIRS and child.mtime > mtime:
                mtime = child.mtime
            kids.append(child)
            if rule is not None:
                self.found.append(Found(rule, e.path, child, node))

        node.mtime = mtime
        node.cat = own or (max(cat_sizes, key=cat_sizes.get) if cat_sizes else "other")

        kids.sort(key=lambda n: n.size, reverse=True)
        kept = [k for k in kids[:KEEP_MAX_CHILDREN] if k.size >= KEEP_MIN_BYTES]
        rest = node.size - sum(k.size for k in kept)
        if rest > 0:
            for k in kept:
                cat_sizes[k.cat] -= k.size
            agg = Node("", False, rest, own or max(cat_sizes, key=cat_sizes.get))
            agg.agg = True
            agg.count = max(1, len(entries) - len(kept))
            kept.append(agg)
        node.children = kept
        return node


def tilde(path: str, home: str) -> str:
    if path == home:
        return "~"
    if path.startswith(home + os.sep):
        return "~/" + path[len(home) + 1:]
    return path


class ScanResult:
    def __init__(self, scanner: Scanner, tree: Node):
        self.tree = tree
        self.root = scanner.root
        self.home = scanner.home
        self.files = scanner.files
        self.dirs = scanner.dirs
        self.errors = scanner.errors
        self.denied = sorted(scanner.denied)
        self.duration = (scanner.finished or time.time()) - (scanner.started or time.time())
        self.finished_at = scanner.finished
        usage = shutil.disk_usage(scanner.root)
        self.disk = {"total": usage.total, "used": usage.used, "free": usage.free}
        self.recs = self._recommendations(scanner)
        self.flags = {i["path"]: r["safety"] for r in self.recs for i in r["items"]}

    def _recommendations(self, scanner: Scanner) -> list:
        now = time.time()
        groups: dict = {}
        for f in scanner.found:
            if f.node.size < MIN_REC_BYTES:
                continue
            idle = None
            if f.rule.idle_days is not None:
                last = f.project.mtime
                idle = int((now - last) / 86400) if last else None
                if idle is not None and idle < f.rule.idle_days:
                    continue
            groups.setdefault(f.rule.id, []).append({
                "path": f.path,
                "display": tilde(f.path, self.home),
                "rel": scanner.rel_of(f.path),
                "size": f.node.size,
                "idle_days": idle,
            })
        recs = []
        for rule in rules.RULES:
            items = groups.get(rule.id)
            if not items:
                continue
            items.sort(key=lambda i: -i["size"])
            if rule.paths or len(items) == 1:
                where = ", ".join(i["display"] for i in items[:2])
                if len(items) > 2:
                    where += f" +{len(items) - 2} more"
            else:
                where = f"{rule.hint} · {len(items)} found"
            recs.append({
                "id": rule.id,
                "title": rule.title,
                "safety": rule.safety,
                "note": rule.note,
                "command": rule.command,
                "where": where,
                "size": sum(i["size"] for i in items),
                "items": items,
            })
        recs.sort(key=lambda r: (r["safety"] != "safe", -r["size"]))
        return recs

    def find(self, rel: str) -> Optional[Node]:
        node = self.tree
        for part in filter(None, rel.split("/")):
            node = node.child(part)
            if node is None or not node.is_dir:
                return None
        return node

    def serialize(self, node: Node, abspath: str, depth: int, level: int = 0) -> dict:
        d = {"n": node.name, "s": node.size, "c": node.cat}
        if node.is_dir:
            d["d"] = 1
        if node.agg:
            d["a"] = node.count
        if node.denied:
            d["x"] = 1
        flag = self.flags.get(abspath)
        if flag:
            d["f"] = flag
        if depth > 0 and node.children:
            limit = (150, 40, 16, 8)[min(level, 3)]
            kids = node.children
            out = [self.serialize(c, os.path.join(abspath, c.name), depth - 1, level + 1)
                   for c in kids[:limit]]
            extra = kids[limit:]
            if extra:
                out.append({"n": "", "s": sum(c.size for c in extra), "c": node.cat,
                            "a": sum(c.count if c.agg else 1 for c in extra)})
            d["k"] = out
        return d
