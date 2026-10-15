"""Lists the disks (mounted volumes) DiskMap can scan."""
from __future__ import annotations

import os
import re
import shutil
import string
import sys
from typing import Optional

# Linux mounts that are never worth offering: boot partitions, snaps, containers.
_LINUX_SKIP_PREFIXES = ("/boot", "/snap", "/var/snap", "/var/lib/docker", "/var/lib/containers")
_LINUX_SKIP_FSTYPES = {"squashfs", "iso9660", "udf", "overlay", "tmpfs", "devtmpfs"}


def _dev(path: str) -> Optional[int]:
    try:
        return os.stat(path).st_dev
    except OSError:
        return None


def _linux_mounts() -> list:
    """(device, mount point) pairs for block-device filesystems, from /proc/mounts."""
    out = []
    try:
        with open("/proc/mounts", encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return out
    for line in lines:
        parts = line.split()
        if len(parts) < 3:
            continue
        device, mount, fstype = parts[0], parts[1], parts[2]
        # /proc/mounts escapes spaces and the like as octal (\040).
        mount = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), mount)
        if not device.startswith("/dev/") or device.startswith("/dev/loop"):
            continue
        if fstype in _LINUX_SKIP_FSTYPES:
            continue
        if any(mount == p or mount.startswith(p + "/") for p in _LINUX_SKIP_PREFIXES):
            continue
        out.append((device, mount))
    return out


def _linux(home: str) -> list:
    mounts = _linux_mounts()
    # The disk holding home: the mount with the longest matching prefix. It goes first.
    home_mount = max((m for m in mounts if home == m[1] or home.startswith(m[1].rstrip("/") + "/")),
                     key=lambda m: len(m[1]), default=None)
    ordered = ([home_mount] if home_mount else []) + sorted(mounts, key=lambda m: m[1])
    seen = set()
    roots = []
    for device, mount in ordered:
        if device in seen:  # same partition mounted twice, or a btrfs subvolume of it
            continue
        seen.add(device)
        label = "System disk (/)" if mount == "/" else os.path.basename(mount) or mount
        roots.append((mount, label, None))
    return roots


def _mac(home: str) -> list:
    try:
        names = sorted(os.listdir("/Volumes"))
    except OSError:
        names = []
    # The startup disk shows up in /Volumes as a link to / named after it ("Macintosh HD").
    startup = next((n for n in names if os.path.islink(os.path.join("/Volumes", n))
                    and os.path.realpath(os.path.join("/Volumes", n)) == "/"), "Macintosh HD")
    # Since Catalina, your files live on a separate Data volume that macOS joins to /
    # (/Users, /Applications…). Scan both, but not the Data volume again under its own path.
    data = "/System/Volumes/Data"
    roots = [("/", startup, data if os.path.isdir(data) else None)]
    for name in names:
        path = os.path.join("/Volumes", name)
        if not os.path.islink(path):
            roots.append((path, name, None))
    return roots


def _windows(home: str) -> list:
    import ctypes

    get_type = ctypes.windll.kernel32.GetDriveTypeW
    home_drive = os.path.splitdrive(home)[0].upper()
    roots = []
    for letter in string.ascii_uppercase:
        path = f"{letter}:\\"
        # 2 = removable, 3 = fixed. Skips network shares, CD/DVD and RAM disks.
        if get_type(path) not in (2, 3) or not os.path.isdir(path):
            continue
        roots.append((path, f"{letter}:", None))
    # The drive holding home (usually C:) first.
    roots.sort(key=lambda r: r[1] != home_drive)
    return roots


def list_disks(home: str) -> list:
    """Mounted disks, the one holding `home` first, as dicts with root, label, total and free.

    "merge" (macOS startup disk only) names a second volume that belongs to the same disk.
    """
    try:
        if sys.platform == "win32":
            found = _windows(home)
        elif sys.platform == "darwin":
            found = _mac(home)
        else:
            found = _linux(home)
    except Exception:  # never let disk discovery break the app
        return []
    out = []
    seen = set()
    for root, label, merge in found:
        dev = _dev(root)
        if dev is None or dev in seen:
            continue
        seen.add(dev)
        try:
            usage = shutil.disk_usage(merge or root)
        except OSError:
            continue
        out.append({"root": os.path.realpath(root), "label": label, "merge": merge,
                    "total": usage.total, "free": usage.free})
    return out
