"""
app.api.deps — common FastAPI dependencies.

Re-exports the canonical implementations of `get_current_user` and `get_db`
so route modules can import a single, consistent path:

    from app.api.deps import get_current_user, get_db

The codebase has historical drift between layouts:
  • get_current_user → app.core.security  (canonical)
                       app.core.permissions (legacy)
  • get_db          → app.core.database  (canonical)
                      app.database       (alt)
                      app.db.session     (very old)

Routes added 2026-05+ (business_plan, kpi, procurement_analysis) all assume
they live in app.api.deps. This shim reconciles that.
"""
from __future__ import annotations

# ─── get_current_user ─────────────────────────────────────────────────
try:
    from app.core.security import get_current_user  # type: ignore[F401]
except ImportError:
    try:
        from app.core.permissions import get_current_user  # type: ignore
    except ImportError as _e:
        raise ImportError(
            "app.api.deps: cannot resolve get_current_user — "
            "checked app.core.security and app.core.permissions. "
            "Update this shim with the correct module path."
        ) from _e


# ─── get_db ───────────────────────────────────────────────────────────
try:
    from app.core.database import get_db  # type: ignore[F401]
except ImportError:
    try:
        from app.database import get_db  # type: ignore
    except ImportError:
        try:
            from app.db.session import get_db_session as get_db  # type: ignore
        except ImportError as _e:
            raise ImportError(
                "app.api.deps: cannot resolve get_db — "
                "checked app.core.database, app.database, app.db.session. "
                "Update this shim with the correct module path."
            ) from _e


__all__ = ["get_current_user", "get_db"]
