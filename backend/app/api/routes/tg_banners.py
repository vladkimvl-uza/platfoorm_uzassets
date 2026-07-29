"""Public banner images for Telegram message headers (Phase B).

Telegram fetches `photo` URLs server-side, so the route is intentionally
unauthenticated. The generator is cached on disk; subsequent requests are
near-instant.

Routes:
    GET /tg-banners/{module}/{severity}.png  → image/png
    GET /tg-banners/                         → JSON listing of valid pairs
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.services import tg_banner

log = logging.getLogger(__name__)

router = APIRouter(prefix="/tg-banners", tags=["telegram-banners"])

_PNG_HEADERS = {
    # 1 day client-cache; ETag-style validation via BANNER_VERSION in body
    "Cache-Control": "public, max-age=86400, immutable",
    "Content-Type": "image/png",
}


@router.get("/", include_in_schema=False)
async def list_banners():
    """List allowed (module, severity) combinations + sample URLs."""
    modules = tg_banner.list_modules()
    severities = tg_banner.list_severities()
    return {
        "version": tg_banner.BANNER_VERSION,
        "modules": modules,
        "severities": severities,
        "example": "/tg-banners/kpi/warning.png",
        "total": len(modules) * len(severities),
    }


@router.get("/{module}/{severity}.png", responses={
    200: {"content": {"image/png": {}}, "description": "PNG banner"},
    400: {"description": "Unknown module or severity"},
})
async def get_banner(
    module: str, severity: str,
    m: Optional[str] = Query(None, max_length=32, description="headline metric"),
    lang: str = Query("ru", max_length=12, description="recipient UI locale"),
) -> Response:
    """Render (or serve cached) banner for (module, severity).
    Optional `?m=$12.4M` query adds a big focal metric to the banner.
    """
    try:
        data = tg_banner.get_banner_bytes(
            module, severity, headline_metric=m, locale=lang,
        )
    except Exception as e:
        log.warning("tg-banner render failed: %s/%s → %s", module, severity, e, exc_info=True)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"banner render failed: {e}",
        )

    headers = dict(_PNG_HEADERS)
    headers["ETag"] = f'W/"{tg_banner.BANNER_VERSION}"'
    return Response(content=data, media_type="image/png", headers=headers)
