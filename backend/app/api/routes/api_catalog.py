"""API Catalog routes (Pack 12.0).

Exposes a dynamic, enriched catalog of all FastAPI endpoints:
  - GET /api-catalog/summary            — list view (modules + endpoints w/ permissions)
  - GET /api-catalog/openapi.json       — raw FastAPI OpenAPI 3.x
  - GET /api-catalog/openapi.enriched.json — same but with permission codes attached
  - GET /api-catalog/scopes             — all permissions usable as scopes, grouped
  - GET /api-catalog/postman.json       — Postman v2.1 collection (export)

Try-it-out (Pack 12.3) and gRPC/GraphQL exports come in later packs.
"""
from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_permission
from app.database import get_db
from app.models.user import Permission, User
from app.schemas.api_key import (
    CatalogEndpoint, CatalogModule, CatalogSummary,
    ScopeItem, ScopeListResponse,
)


router = APIRouter(prefix="/api-catalog", tags=["api-catalog"])


# ════════════════════════════════════════════════════════════
#   Internal: extract permission codes from route dependencies
# ════════════════════════════════════════════════════════════

# `Depends(require_permission("foo.bar"))` becomes a closure; we recover the
# `code` parameter from the dependency factory by inspecting its closure cells.
def _extract_required_permission(route) -> str | None:
    deps = getattr(route, "dependant", None)
    if deps is None:
        return None
    queue = list(deps.dependencies)
    while queue:
        d = queue.pop(0)
        call = getattr(d, "call", None)
        if call is not None and getattr(call, "__name__", "") == "_dep":
            closure = getattr(call, "__closure__", None) or ()
            for cell in closure:
                try:
                    v = cell.cell_contents
                except ValueError:
                    continue
                if isinstance(v, str) and "." in v and len(v) < 64:
                    return v
        # Recurse into sub-dependencies
        queue.extend(getattr(d, "dependencies", []) or [])
    return None


# Module → friendly group mapping. Keys are module prefixes; values are the group.
_MODULE_GROUPS = {
    "auth": "Авторизация · доступ",        "rbac": "Авторизация · доступ",
    "companies": "Портфель",               "projects": "Портфель",
    "tasks": "Портфель",                   "boards": "Портфель",
    "comments": "Портфель",                "sectors": "Портфель",
    "financials": "Финансы",               "ratings": "Финансы",
    "dashboard": "Финансы",                "executive_dashboard": "Финансы",
    "finmodel_storage": "Финансы",         "business_plan": "Финансы",
    "credit_portfolio": "Инвестиции",      "invest_projects": "Инвестиции",
    "procurement_analysis": "Инвестиции",
    "notifications": "Pack 11 · уведомления",
    "moderation":    "Pack 11 · уведомления",
    "admin_broadcasts": "Pack 11 · уведомления",
    "broadcasts":     "Pack 11 · уведомления",
    "api_catalog":   "Pack 12 · API & Интеграции",
    "api_keys":      "Pack 12 · API & Интеграции",
    "service_accounts": "Pack 12 · API & Интеграции",
}


def _module_from_tags_or_path(tags: list[str] | None, path: str) -> str:
    if tags:
        # Prefer the first tag, slugged
        t = tags[0]
        return t.replace("-", "_").lower()
    # Fallback: first path segment
    seg = path.strip("/").split("/")[0] if path else ""
    return seg.replace("-", "_").lower()


# ════════════════════════════════════════════════════════════
#   Routes
# ════════════════════════════════════════════════════════════

@router.get("/summary", response_model=CatalogSummary)
async def catalog_summary(
    request: Request,
    _u: User = Depends(require_permission("api_catalog.read")),
):
    """Enriched flat view: modules + endpoints with their required permissions."""
    import logging
    log = logging.getLogger(__name__)

    app = request.app
    try:
        schema = app.openapi()
    except Exception as e:
        log.exception("app.openapi() failed")
        # Fall back to minimal info dict instead of crashing the whole endpoint
        schema = {"info": {"title": "UzAssets API", "version": "0.0.0"}}

    endpoints: list[CatalogEndpoint] = []
    module_counter: dict[str, int] = {}
    skipped = 0

    for route in app.routes:
        try:
            # WebSocket / Mount / static routes don't have .methods
            if not hasattr(route, "methods") or not getattr(route, "path", None):
                if hasattr(route, "path") and getattr(route, "endpoint", None) and \
                   getattr(route, "path", "").startswith("/"):
                    # WebSocket route
                    module = _module_from_tags_or_path(None, route.path)
                    endpoints.append(CatalogEndpoint(
                        path=route.path,
                        method="WEBSOCKET",
                        operation_id=getattr(route, "name", None),
                        summary="WebSocket stream",
                        description=None,
                        tags=[],
                        module=module,
                        required_permission=None,
                    ))
                    module_counter[module] = module_counter.get(module, 0) + 1
                continue

            for method in (m for m in (route.methods or []) if m not in {"HEAD", "OPTIONS"}):
                tags = list(getattr(route, "tags", None) or [])
                path = getattr(route, "path", "") or ""
                module = _module_from_tags_or_path(tags, path)
                try:
                    perm = _extract_required_permission(route)
                except Exception:
                    perm = None

                summary = getattr(route, "summary", None)
                description = getattr(route, "description", None)
                if not summary and description:
                    summary = description.split("\n", 1)[0][:200]

                endpoints.append(CatalogEndpoint(
                    path=path,
                    method=method,
                    operation_id=getattr(route, "operation_id", None) or getattr(route, "name", None),
                    summary=summary,
                    description=description,
                    tags=tags,
                    module=module,
                    required_permission=perm,
                    deprecated=bool(getattr(route, "deprecated", False)),
                ))
                module_counter[module] = module_counter.get(module, 0) + 1
        except Exception as e:
            skipped += 1
            log.warning(f"Skipped route {getattr(route, 'path', '?')}: {type(e).__name__}: {e}")
            continue

    if skipped > 0:
        log.info(f"Catalog summary: skipped {skipped} routes due to introspection errors")

    modules = [
        CatalogModule(
            name=m,
            group=_MODULE_GROUPS.get(m, "Прочее"),
            endpoints_count=cnt,
        )
        for m, cnt in sorted(module_counter.items())
    ]

    return CatalogSummary(
        title=schema.get("info", {}).get("title", "UzAssets API"),
        version=schema.get("info", {}).get("version", "0.0.0"),
        total_endpoints=len(endpoints),
        modules=modules,
        endpoints=endpoints,
    )


@router.get("/openapi.json")
async def openapi_raw(
    request: Request,
    _u: User = Depends(require_permission("api_catalog.read")),
):
    """Raw FastAPI OpenAPI 3.x spec (same as /openapi.json on root)."""
    return JSONResponse(request.app.openapi())


@router.get("/openapi.enriched.json")
async def openapi_enriched(
    request: Request,
    _u: User = Depends(require_permission("api_catalog.read")),
):
    """OpenAPI spec with `x-required-permission` extension added per operation.

    Useful for SDK generators that want to know which scope is required.
    """
    import logging
    log = logging.getLogger(__name__)
    try:
        spec = json.loads(json.dumps(request.app.openapi()))  # deep copy
    except Exception:
        log.exception("openapi.enriched: app.openapi() failed")
        raise HTTPException(500, "OpenAPI spec generation failed; see backend logs")

    for route in request.app.routes:
        try:
            if not hasattr(route, "methods"):
                continue
            perm = _extract_required_permission(route)
            if not perm or route.path not in spec.get("paths", {}):
                continue
            for method in (m.lower() for m in (route.methods or []) if m not in {"HEAD", "OPTIONS"}):
                op = spec["paths"][route.path].get(method)
                if op is not None:
                    op["x-required-permission"] = perm
        except Exception as e:
            log.warning(f"openapi.enriched: skipped route {getattr(route, 'path', '?')}: {e}")
            continue

    spec.setdefault("info", {})["x-platform"] = "UzAssets"
    return JSONResponse(spec)


@router.get("/scopes", response_model=ScopeListResponse)
async def list_scopes(
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("api_catalog.read")),
):
    """All permissions in the system — usable as scopes when issuing API keys."""
    rows = (await db.execute(
        select(Permission).order_by(Permission.module, Permission.code),
    )).scalars().all()

    items = [
        ScopeItem(code=p.code, name=p.name, module=p.module, description=p.description)
        for p in rows
    ]
    grouped: dict[str, list[ScopeItem]] = {}
    for it in items:
        key = it.module or "general"
        grouped.setdefault(key, []).append(it)

    return ScopeListResponse(items=items, grouped_by_module=grouped)


@router.get("/postman.json")
async def export_postman(
    request: Request,
    _u: User = Depends(require_permission("api_catalog.read")),
):
    """Generate Postman v2.1 collection from the OpenAPI spec.

    Simplified converter — sufficient for browsing & manual smoke testing.
    Use a full openapi2postman tool for production-grade conversion.
    """
    spec = request.app.openapi()
    info = spec.get("info", {})
    base_url = "{{baseUrl}}"

    collection: dict[str, Any] = {
        "info": {
            "name":         info.get("title", "UzAssets API"),
            "description":  info.get("description", "Auto-generated from OpenAPI."),
            "version":      info.get("version", "0.0.0"),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "auth": {
            "type": "bearer",
            "bearer": [{"key": "token", "value": "{{accessToken}}", "type": "string"}],
        },
        "variable": [
            {"key": "baseUrl",     "value": "https://platform.uz-assets.uz/api"},
            {"key": "accessToken", "value": "", "type": "string"},
        ],
        "item": [],
    }

    # Group by tag → Postman folders
    groups: dict[str, list] = {}
    for path, methods in (spec.get("paths") or {}).items():
        for method, op in (methods or {}).items():
            if method.upper() not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                continue
            tag = (op.get("tags") or ["misc"])[0]
            url_parts = [p for p in path.strip("/").split("/") if p]
            req = {
                "name": op.get("summary") or f"{method.upper()} {path}",
                "request": {
                    "method": method.upper(),
                    "header": [{"key": "Content-Type", "value": "application/json"}],
                    "url": {
                        "raw":  f"{base_url}{path}",
                        "host": [base_url],
                        "path": url_parts,
                    },
                    "description": op.get("description") or "",
                },
            }
            if op.get("requestBody"):
                req["request"]["body"] = {
                    "mode": "raw",
                    "raw":  json.dumps({"_": "see schema in API catalog"}, indent=2),
                    "options": {"raw": {"language": "json"}},
                }
            groups.setdefault(tag, []).append(req)

    for tag, items in sorted(groups.items()):
        collection["item"].append({"name": tag, "item": items})

    name_slug = re.sub(r"[^a-z0-9-]+", "-", info.get("title", "uzassets").lower())[:48].strip("-")
    return Response(
        content=json.dumps(collection, indent=2, ensure_ascii=False).encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{name_slug}.postman_collection.json"'},
    )
