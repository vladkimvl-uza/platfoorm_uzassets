"""Observability: Sentry + Prometheus (Pack 148, P2-11 / P2-12).

Both opt-in via env vars — absent config = no-op so dev environments stay
lean. Production sets SENTRY_DSN and PROMETHEUS_ENABLED=true.

Sentry:
  - PII scrubbing: emails, IPs, JWT tokens removed before send
  - Sample rate configurable
  - Auto-captures FastAPI / SQLAlchemy / HTTPX spans when traces enabled

Prometheus:
  - Counters for security-relevant events (failed login, lockout, 4xx/5xx,
    audit chain status, MFA verify, password change)
  - /metrics endpoint protected by Basic auth (PROMETHEUS_METRICS_USER /
    PROMETHEUS_METRICS_PASSWORD env) so it's not scrape-able by anonymous
    public.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


# =====================================================================
# Sentry
# =====================================================================

_SENTRY_INITIALIZED = False


def init_sentry() -> bool:
    """Initialize sentry-sdk if SENTRY_DSN is set. Idempotent; returns True
    if initialization happened (or was already done), False if disabled.
    """
    global _SENTRY_INITIALIZED
    if _SENTRY_INITIALIZED:
        return True
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        logger.info("Sentry disabled (SENTRY_DSN not set)")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    except ImportError:
        logger.warning("sentry-sdk not installed — skipping Sentry init")
        return False

    env = os.environ.get("ENVIRONMENT", "unknown")
    traces_sample_rate = float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.0"))
    profiles_sample_rate = float(os.environ.get("SENTRY_PROFILES_SAMPLE_RATE", "0.0"))
    release = os.environ.get("SENTRY_RELEASE") or os.environ.get("GIT_SHA")

    sentry_sdk.init(
        dsn=dsn,
        environment=env,
        release=release,
        traces_sample_rate=traces_sample_rate,
        profiles_sample_rate=profiles_sample_rate,
        send_default_pii=False,          # CRITICAL: don't ship raw user IPs/emails
        before_send=_sentry_before_send,
        before_send_transaction=_sentry_before_send,
        integrations=[
            FastApiIntegration(),
            StarletteIntegration(),
            SqlalchemyIntegration(),
        ],
    )
    _SENTRY_INITIALIZED = True
    logger.info(
        f"Sentry initialized env={env} traces={traces_sample_rate} "
        f"profiles={profiles_sample_rate} release={release}"
    )
    return True


# Regex to redact obvious PII before Sentry ingestion. Belt-and-suspenders on
# top of send_default_pii=False.
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\b")
_BEARER_RE = re.compile(r"(?i)(?:bearer|api[_\-]?key)\s+[A-Za-z0-9_\-.]+")


def _scrub_string(s: str) -> str:
    if not isinstance(s, str):
        return s
    s = _EMAIL_RE.sub("[email]", s)
    s = _IPV4_RE.sub("[ipv4]", s)
    s = _JWT_RE.sub("[jwt]", s)
    s = _BEARER_RE.sub("[token]", s)
    return s


def _scrub_obj(obj: Any) -> Any:
    if isinstance(obj, str):
        return _scrub_string(obj)
    if isinstance(obj, dict):
        return {k: _scrub_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_scrub_obj(x) for x in obj]
    return obj


def _sentry_before_send(event: dict, hint: dict) -> Optional[dict]:
    """Final PII scrub before event is sent to Sentry server."""
    try:
        # Strip user IP / email even if Sentry tries to attach them
        user = event.get("user")
        if isinstance(user, dict):
            user.pop("ip_address", None)
            user.pop("email", None)
            if "username" in user and isinstance(user["username"], str):
                user["username"] = _scrub_string(user["username"])
        # Scrub request body / headers / query / breadcrumbs
        for key in ("request", "extra", "tags", "breadcrumbs", "contexts"):
            if key in event:
                event[key] = _scrub_obj(event[key])
        # Scrub the top-level message + exception values
        if "message" in event:
            event["message"] = _scrub_string(event["message"])
        for ex in (event.get("exception", {}).get("values") or []):
            if "value" in ex:
                ex["value"] = _scrub_string(ex["value"])
    except Exception:
        # Never let scrubbing failure drop the event
        pass
    return event


# =====================================================================
# Prometheus
# =====================================================================

_PROM_REGISTRY: Any = None
_METRICS: dict[str, Any] = {}


def init_prometheus() -> bool:
    """Set up Prometheus counters + gauges. Returns True if enabled."""
    global _PROM_REGISTRY, _METRICS
    if os.environ.get("PROMETHEUS_ENABLED", "").strip().lower() != "true":
        logger.info("Prometheus disabled (set PROMETHEUS_ENABLED=true to enable)")
        return False
    try:
        from prometheus_client import Counter, Gauge, Histogram, CollectorRegistry
    except ImportError:
        logger.warning("prometheus-client not installed — skipping init")
        return False

    _PROM_REGISTRY = CollectorRegistry()

    _METRICS["http_requests_total"] = Counter(
        "uza_http_requests_total",
        "Total HTTP requests, by method + status class",
        labelnames=("method", "status_class"),
        registry=_PROM_REGISTRY,
    )
    _METRICS["auth_login_total"] = Counter(
        "uza_auth_login_total",
        "Login attempts, by outcome (success / failed / locked)",
        labelnames=("outcome",),
        registry=_PROM_REGISTRY,
    )
    _METRICS["auth_mfa_verify_total"] = Counter(
        "uza_auth_mfa_verify_total",
        "MFA code verification attempts, by outcome",
        labelnames=("outcome",),
        registry=_PROM_REGISTRY,
    )
    _METRICS["auth_password_change_total"] = Counter(
        "uza_auth_password_change_total",
        "Password change events, by source (self / admin_reset / forced_expiry)",
        labelnames=("source",),
        registry=_PROM_REGISTRY,
    )
    _METRICS["audit_chain_status"] = Gauge(
        "uza_audit_chain_status",
        "Audit chain integrity: 1=OK, 0=BROKEN. Set by hourly verifier.",
        registry=_PROM_REGISTRY,
    )
    _METRICS["audit_chain_rows"] = Gauge(
        "uza_audit_chain_rows",
        "Audit chain row count at last verification.",
        registry=_PROM_REGISTRY,
    )
    _METRICS["request_duration_seconds"] = Histogram(
        "uza_request_duration_seconds",
        "HTTP request duration",
        labelnames=("method",),
        buckets=(0.005, 0.025, 0.1, 0.5, 1.0, 2.5, 10.0),
        registry=_PROM_REGISTRY,
    )
    logger.info("Prometheus metrics registered (uza_*)")
    return True


def get_registry():
    return _PROM_REGISTRY


def incr(metric_name: str, **labels) -> None:
    """Increment a counter by name. No-op if Prometheus disabled / metric not
    registered. Caller doesn't need to check enabled state.
    """
    metric = _METRICS.get(metric_name)
    if metric is None:
        return
    try:
        if labels:
            metric.labels(**labels).inc()
        else:
            metric.inc()
    except Exception:
        pass


def gauge_set(metric_name: str, value: float, **labels) -> None:
    metric = _METRICS.get(metric_name)
    if metric is None:
        return
    try:
        if labels:
            metric.labels(**labels).set(value)
        else:
            metric.set(value)
    except Exception:
        pass


def observe(metric_name: str, value: float, **labels) -> None:
    metric = _METRICS.get(metric_name)
    if metric is None:
        return
    try:
        if labels:
            metric.labels(**labels).observe(value)
        else:
            metric.observe(value)
    except Exception:
        pass
