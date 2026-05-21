"""Disk cache for rendered banner PNGs (Phase B).

Cache dir is configurable via TG_BANNER_CACHE_DIR (default /var/cache/tg-banners).
Key is sha1(module|severity|version) — bumping BANNER_VERSION invalidates.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Optional


def cache_dir() -> Path:
    raw = os.getenv("TG_BANNER_CACHE_DIR", "/var/cache/tg-banners")
    p = Path(raw)
    try:
        p.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError):
        # Fall back to /tmp when /var/cache isn't writable (rootless dev)
        p = Path("/tmp/tg-banners")
        p.mkdir(parents=True, exist_ok=True)
    return p


def _key(module: str, severity: str, version: str) -> str:
    h = hashlib.sha1(f"{module}|{severity}|{version}".encode("utf-8")).hexdigest()
    return f"{h}.png"


def get(module: str, severity: str, version: str) -> Optional[bytes]:
    """Return cached PNG bytes for (module, severity, version), or None."""
    path = cache_dir() / _key(module, severity, version)
    if not path.exists():
        return None
    try:
        return path.read_bytes()
    except OSError:
        return None


def put(module: str, severity: str, version: str, data: bytes) -> None:
    """Atomically write cached PNG to disk. Errors are swallowed (best-effort)."""
    path = cache_dir() / _key(module, severity, version)
    tmp = path.with_suffix(".png.tmp")
    try:
        tmp.write_bytes(data)
        tmp.replace(path)
    except OSError:
        # Don't break the caller if disk is full or permissions broken
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def clear() -> int:
    """Delete every cached PNG. Returns number of files removed."""
    n = 0
    for p in cache_dir().glob("*.png"):
        try:
            p.unlink()
            n += 1
        except OSError:
            pass
    return n
