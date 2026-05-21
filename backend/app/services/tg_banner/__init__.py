"""Telegram banner generation (Phase B).

Renders 600×120px PNG banners with UzAssets branding for the top of bot
notifications. Banners are keyed by (module, severity, version) and cached
on disk so the generator runs at most once per combination.

Public API:
    get_banner_bytes(module, severity) -> bytes
    get_banner_url(base_url, module, severity) -> str
    list_modules() / list_severities() -> list[str]
    BANNER_VERSION — bump to invalidate disk cache
"""
from .generator import (
    BANNER_VERSION,
    get_banner_bytes,
    get_banner_url,
    list_modules,
    list_severities,
)

__all__ = [
    "BANNER_VERSION",
    "get_banner_bytes",
    "get_banner_url",
    "list_modules",
    "list_severities",
]
