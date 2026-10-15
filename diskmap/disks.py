"""Lists the disks (mounted volumes) DiskMap can scan besides your home folder."""
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
    # The device holding home: the mount with the longest matching prefix.
    home_dev = None
    best = -1
    for device, mount in mounts:
        if (home == mount or home.startswith(mount.rstrip("/") + "/")) and len(mount) > best:
            home_dev, best = device, len(mount)
    seen = {home_dev}
    roots = []
    for device, mount in sorted(mounts, key=lambda m: m[1]):
        if device in seen:  # same partition mounted twice, or a btrfs subvolume of it
            continue
        seen.add(device)
        label = "System disk (/)" if mount == "/" else os.path.basename(mount) or mount
        roots.append((mount, label))
    return roots


def _mac(home: str) -> list:
    roots = []
    try:
        names = sorted(os.listdir("/Volumes"))
    except OSError:
        return roots
    for name in names:
        path = os.path.join("/Volumes", name)
        if os.path.islink(path):  # "Macintosh HD" -> /, the disk home lives on
            continue
        roots.append((path, name))
    return roots


def _windows(home: str) -> list:
    import ctypes

    get_type = ctypes.windll.kernel32.GetDriveTypeW
    roots = []
    for letter in string.ascii_uppercase:
        path = f"{letter}:\\"
        # 2 = removable, 3 = fixed. Skips network shares, CD/DVD and RAM disks.
        if get_type(path) not in (2, 3) or not os.path.isdir(path):
            continue
        roots.append((path, f"{letter}:"))
    return roots


def other_disks(home: str) -> list:
    """Disks other than the one holding `home`, as dicts with root, label, total and free."""
    try:
        if sys.platform == "win32":
            found = _windows(home)
        elif sys.platform == "darwin":
            found = _mac(home)
        else:
            found = _linux(home)
    except Exception:  # never let disk discovery break the app
        return []
    home_dev = _dev(home)
    out = []
    seen = {home_dev}
    for root, label in found:
        dev = _dev(root)
        if dev is None or dev in seen:
            continue
        seen.add(dev)
        try:
            usage = shutil.disk_usage(root)
        except OSError:
            continue
        out.append({"root": os.path.realpath(root), "label": label,
                    "total": usage.total, "free": usage.free})
    return out
