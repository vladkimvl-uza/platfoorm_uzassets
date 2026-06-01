"""Prometheus /metrics endpoint with Basic auth (Pack 148, P2-12).

Scrape config example:
    scrape_configs:
      - job_name: uzassets-backend
        metrics_path: /metrics
        scheme: https
        basic_auth:
          username: prometheus
          password: <from env>
        static_configs:
          - targets: [platform.uz-assets.uz]
"""
from __future__ import annotations

import hmac
import os
import secrets

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

router = APIRouter(tags=["metrics"])
_security = HTTPBasic(auto_error=False)


def _check_basic_auth(creds: HTTPBasicCredentials | None) -> None:
    """Validate scrape credentials via constant-time comparison."""
    user = os.environ.get("PROMETHEUS_METRICS_USER", "").strip()
    pwd  = os.environ.get("PROMETHEUS_METRICS_PASSWORD", "").strip()
    if not user or not pwd:
        # No credentials configured → endpoint disabled.
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if creds is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="metrics auth required",
            headers={"WWW-Authenticate": 'Basic realm="prometheus"'},
        )
    ok_user = hmac.compare_digest(creds.username.encode(), user.encode())
    ok_pwd  = hmac.compare_digest(creds.password.encode(), pwd.encode())
    if not (ok_user and ok_pwd):
        # Constant-time burn even on failure
        secrets.compare_digest("a", "b")
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="invalid metrics credentials",
            headers={"WWW-Authenticate": 'Basic realm="prometheus"'},
        )


@router.get("/metrics")
async def metrics(creds: HTTPBasicCredentials | None = Depends(_security)):
    _check_basic_auth(creds)
    try:
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

        from app.core.observability import get_registry
    except ImportError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "prometheus-client not installed")
    reg = get_registry()
    if reg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Prometheus not initialized")
    return Response(content=generate_latest(reg), media_type=CONTENT_TYPE_LATEST)
