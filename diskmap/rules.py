"""Categories and cleanup rules.

Paths in this file are relative to the user's home folder and always use "/".
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

CATEGORIES = {
    "media": "Documents & media",
    "other": "Dev tools & other",
    "code": "Code projects",
    "sdk": "iOS & Android SDKs",
    "ai": "AI models",
    "cache": "Package caches",
}

# Exact home-relative directory -> category. Descendants inherit it, and a more
# specific entry (e.g. ".cache/huggingface" under ".cache") overrides its parent.
PATH_CATEGORIES = {
    "Documents": "media",
    "Desktop/Screenshots": "media",
    "Pictures": "media",
    "Movies": "media",
    "Music": "media",
    "Downloads": "media",
    "Videos": "media",
    "OneDrive": "media",
    "Library/Mobile Documents": "media",
    "Library/CloudStorage": "media",
    "Library/Messages": "media",
    "Library/Mail": "media",
    "Library/Photos": "media",

    ".ollama": "ai",
    ".cache/huggingface": "ai",
    ".cache/lm-studio": "ai",
    ".lmstudio": "ai",
    ".cache/torch": "ai",
    ".cache/whisper": "ai",
    "Library/Application Support/LM Studio": "ai",
    "Library/Application Support/Ollama": "ai",

    "Library/Developer": "sdk",
    "Library/Android": "sdk",
    ".android": "sdk",
    "Android": "sdk",
    "Library/Application Support/Google/AndroidStudio": "sdk",
    "AppData/Local/Android": "sdk",
    "AppData/Local/Google/AndroidStudio": "sdk",

    ".npm": "cache",
    ".gradle": "cache",
    ".cache": "cache",
    ".cargo": "cache",
    ".m2": "cache",
    ".pnpm-store": "cache",
    ".yarn": "cache",
    ".bun": "cache",
    ".cocoapods": "cache",
    ".nuget": "cache",
    ".pub-cache": "cache",
    "go/pkg/mod": "cache",
    "Library/Caches": "cache",
    "Library/pnpm": "cache",
    "AppData/Local/npm-cache": "cache",
    "AppData/Local/Yarn": "cache",
    "AppData/Local/pnpm": "cache",
    "AppData/Local/pip": "cache",
    "AppData/Local/uv": "cache",
    "AppData/Local/pypoetry": "cache",
    "AppData/Local/ms-playwright": "cache",
    ".local/share/pnpm": "cache",

    ".vscode": "other",
    ".cursor": "other",
    ".rustup": "other",
    ".nvm": "other",
    ".pyenv": "other",
    ".docker": "other",
    ".Trash": "other",
    "Applications": "other",
    "Library/Containers/com.docker.docker": "other",
    "AppData": "other",
    "AppData/Local/Docker": "other",
    ".local/share/Trash": "other",
}

# A directory containing any of these is treated as a code project.
PROJECT_MARKERS = frozenset({
    ".git", "package.json", "pyproject.toml", "setup.py", "requirements.txt",
    "Cargo.toml", "go.mod", "pom.xml", "build.gradle", "build.gradle.kts",
    "Gemfile", "Package.swift", "composer.json", "pubspec.yaml", "deno.json",
})

# Changes inside these folders don't count as "working on the project" when
# deciding whether a project is idle.
QUIET_DIRS = frozenset({
    "node_modules", ".git", ".next", ".turbo", ".nuxt", ".svelte-kit", ".parcel-cache",
    ".angular", "target", ".venv", "venv", "__pycache__", "dist", "build", ".cache",
    ".gradle", ".idea", ".claude", ".pytest_cache", ".mypy_cache", ".ruff_cache",
})

_MEDIA_EXT = frozenset("""
jpg jpeg png gif heic heif webp tif tiff bmp raw cr2 cr3 nef arw dng psd ai svg
mp4 mov m4v avi mkv webm mpg mpeg 3gp mp3 m4a aac wav flac aiff aif ogg opus
pdf doc docx xls xlsx ppt pptx key pages numbers txt rtf md epub csv odt ods
""".split())
_AI_EXT = frozenset("gguf safetensors ckpt pt pth onnx mlmodel mlpackage tflite".split())


def file_category(name: str) -> str:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext in _MEDIA_EXT:
        return "media"
    if ext in _AI_EXT:
        return "ai"
    return "other"


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    safety: str                      # "safe" | "review"
    note: str
    paths: tuple = ()                # home-relative directories
    names: tuple = ()                # directory names matched anywhere in your projects
    hint: str = ""                   # how name-matched items are described in the UI
    parent: Optional[str] = None     # name rule: required parent directory name
    sibling: Optional[str] = None    # name rule: file that must sit next to the directory
    inside: Optional[str] = None     # name rule: file that must exist inside the directory
    idle_days: Optional[int] = None  # name rule: only when the project is untouched this long
    command: Optional[str] = None    # run this instead of deleting the paths


RULES = [
    # ---- Safe: caches and build output that tools recreate on demand ----
    Rule("npm", "npm cache", "safe", "Re-downloaded by npm when needed.",
         paths=(".npm/_cacache", ".npm/_npx",
                "AppData/Local/npm-cache/_cacache", "AppData/Local/npm-cache/_npx")),
    Rule("yarn", "Yarn cache", "safe", "Re-downloaded by Yarn when needed.",
         paths=("Library/Caches/Yarn", ".cache/yarn", ".yarn/berry/cache", "AppData/Local/Yarn/Cache")),
    Rule("pnpm", "pnpm store", "safe", "Projects re-link packages on the next pnpm install.",
         paths=("Library/pnpm/store", ".local/share/pnpm/store", ".pnpm-store", "AppData/Local/pnpm/store")),
    Rule("bun", "Bun cache", "safe", "Re-downloaded by Bun when needed.",
         paths=(".bun/install/cache",)),
    Rule("jsbuild", "Next.js & Turbo build output", "safe",
         "Regenerated on the next dev server start or build.",
         names=(".next", ".turbo", ".nuxt", ".svelte-kit", ".parcel-cache", ".angular"),
         hint="**/.next, .turbo, .nuxt…"),
    Rule("cargo-target", "Rust build output", "safe", "Rebuilt by cargo (first build will be slow).",
         names=("target",), sibling="Cargo.toml", hint="**/target (Rust)"),
    Rule("cargo", "Cargo registry cache", "safe", "Re-downloaded by cargo when needed.",
         paths=(".cargo/registry",)),
    Rule("gradle", "Gradle caches", "safe", "Re-downloaded on the next Gradle build.",
         paths=(".gradle/caches", ".gradle/wrapper/dists", ".gradle/daemon")),
    Rule("maven", "Maven repository", "safe", "Re-downloaded on the next Maven build.",
         paths=(".m2/repository",)),
    Rule("xcode-dd", "Xcode DerivedData", "safe", "Xcode rebuilds it; close Xcode first.",
         paths=("Library/Developer/Xcode/DerivedData",)),
    Rule("xcode-ds", "Xcode device support files", "safe",
         "Re-copied the next time you connect a device.",
         paths=("Library/Developer/Xcode/iOS DeviceSupport",
                "Library/Developer/Xcode/watchOS DeviceSupport",
                "Library/Developer/Xcode/tvOS DeviceSupport")),
    Rule("pycache", "uv & pip caches", "safe", "Re-downloaded by uv / pip when needed.",
         paths=(".cache/uv", "Library/Caches/uv", ".cache/pip", "Library/Caches/pip",
                "Library/Caches/pypoetry", ".cache/pypoetry",
                "AppData/Local/uv/cache", "AppData/Local/pip/Cache", "AppData/Local/pypoetry/Cache")),
    Rule("browsers", "Puppeteer & Playwright browsers", "safe",
         "Re-downloaded on the next install / test run.",
         paths=(".cache/puppeteer", ".cache/ms-playwright", "Library/Caches/ms-playwright",
                "AppData/Local/ms-playwright")),
    Rule("brew", "Homebrew download cache", "safe", "Old bottles and downloads.",
         paths=("Library/Caches/Homebrew", ".cache/Homebrew"), command="brew cleanup --prune=all"),
    Rule("cocoapods", "CocoaPods cache", "safe", "Re-downloaded by pod install.",
         paths=("Library/Caches/CocoaPods",)),
    Rule("jetbrains", "JetBrains IDE caches", "safe", "Indexes are rebuilt on next launch.",
         paths=("Library/Caches/JetBrains", ".cache/JetBrains")),
    Rule("go", "Go module cache", "safe", "Re-downloaded by go when needed.",
         paths=("go/pkg/mod",), command="go clean -modcache"),

    # ---- Review first: big, but you may still want them ----
    Rule("android", "Android SDK & emulators", "review",
         "Includes system images and emulator disks; Android Studio can reinstall them.",
         paths=("Library/Android/sdk", "Android/Sdk", "AppData/Local/Android/Sdk", ".android/avd")),
    Rule("simulators", "iOS simulators", "review",
         "Removes simulator devices and their data. Xcode recreates default ones.",
         paths=("Library/Developer/CoreSimulator/Devices",),
         command="xcrun simctl delete all"),
    Rule("xcode-archives", "Xcode archives", "review",
         "Needed to symbolicate crash reports for builds you shipped.",
         paths=("Library/Developer/Xcode/Archives",)),
    Rule("ollama", "Ollama models", "review", "Re-download with `ollama pull` if you need them again.",
         paths=(".ollama/models",)),
    Rule("hf", "Hugging Face models", "review", "Re-downloaded on next use, can be large.",
         paths=(".cache/huggingface",)),
    Rule("lmstudio", "LM Studio models", "review", "Re-download from LM Studio if needed.",
         paths=(".lmstudio/models", ".cache/lm-studio/models")),
    Rule("worktrees", "Claude Code worktrees", "review",
         "Make sure nothing uncommitted is left; run `git worktree prune` afterwards.",
         names=("worktrees",), parent=".claude", hint="**/.claude/worktrees"),
    Rule("node_modules", "node_modules in idle projects", "review",
         "Projects untouched for 30+ days. Run your package manager's install to restore.",
         names=("node_modules",), idle_days=30, hint="**/node_modules (idle 30d+)"),
    Rule("venv", "Python venvs in idle projects", "review",
         "Projects untouched for 30+ days. Recreate with `uv sync` / `pip install`.",
         names=(".venv", "venv"), inside="pyvenv.cfg", idle_days=30, hint="**/.venv (idle 30d+)"),
    Rule("docker", "Docker Desktop disk image", "review",
         "Deletes unused images, containers and build cache. Docker must be running.",
         paths=("Library/Containers/com.docker.docker/Data/vms", "AppData/Local/Docker/wsl"),
         command="docker system prune -a"),
    Rule("trash", "Trash", "review", "Files you already deleted.",
         paths=(".Trash", ".local/share/Trash")),
    Rule("temp", "Temporary files", "review",
         "Windows temp folder. Files in use are skipped; close apps first.",
         paths=("AppData/Local/Temp",)),
]

_PATH_INDEX = {p: r for r in RULES for p in r.paths}
_NAME_INDEX: dict = {}
for _r in RULES:
    for _n in _r.names:
        _NAME_INDEX.setdefault(_n, []).append(_r)

# Name rules only look inside your own folders, not in tool or app data
# (e.g. node_modules bundled with VS Code extensions must stay).
_NAME_RULE_SKIP_TOP = frozenset({"Library", "Applications", "AppData", "snap"})


def match_dir(name: str, rel: Optional[str], parent_name: str,
              sibling_names: set, path: str) -> Optional[Rule]:
    """Return the cleanup rule that applies to a directory, if any."""
    if rel is not None:
        rule = _PATH_INDEX.get(rel)
        if rule:
            return rule
        top = rel.split("/", 1)[0]
        if top.startswith(".") or top in _NAME_RULE_SKIP_TOP:
            return None
    for rule in _NAME_INDEX.get(name, ()):
        if rule.parent and rule.parent != parent_name:
            continue
        if rule.sibling and rule.sibling not in sibling_names:
            continue
        if rule.inside and not os.path.exists(os.path.join(path, rule.inside)):
            continue
        return rule
    return None
