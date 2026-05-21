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
    CatalogEndpointWithSubstitution, CompanyCatalogResponse,
    TryRequest, TryResponse,
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


# ════════════════════════════════════════════════════════════
#  Phase 5.1 · Per-company catalog + try-it-out
# ════════════════════════════════════════════════════════════

from uuid import UUID
from typing import Optional
from fastapi import Query

from app.core.security import get_current_user
from app.models.company import Company


# Path-segment-after-/companies/{id}/ → tab code mapping (fallback)
_TAB_BY_PATH_SEGMENT = {
    "financials":  "financials",
    "ratings":     "ratings",
    "kpi":         "kpi",
    "businessplan":"kpi",
    "bp":          "kpi",
    "credit-portfolio": "loans",
    "credits":     "loans",
    "loans":       "loans",
    "procurement": "procurement",
    "purchases":   "procurement",
    "forensic":    "procurement",
    "documents":   "documents",
    "shareholders":"identity",
    "esg":         "esg",
    "governance":  "governance",
    "consultants": "consultants",
    "notes":       "notes",
    "projects":    "projects",
    "tasks":       "tasks",
}


def _is_company_scoped(endpoint: CatalogEndpoint) -> bool:
    """An endpoint counts as company-scoped if its path has {id}, {company_id}
    or a /companies/{...}/ segment, OR if it carries a `company.*` tag."""
    p = endpoint.path or ""
    if "{id}" in p or "{company_id}" in p or "{company_code}" in p:
        return True
    if endpoint.tags and any(t.startswith("company.") for t in endpoint.tags):
        return True
    return False


def _endpoint_belongs_to_tab(endpoint: CatalogEndpoint, tab: str) -> bool:
    """Return True if endpoint belongs to the given Detail-view tab.

    1) `tab.<tab>` tag → explicit match
    2) `<tab>` as one of tags → match
    3) Path segment after /companies/{id}/ → mapped via _TAB_BY_PATH_SEGMENT
    """
    for t in (endpoint.tags or []):
        if t == f"tab.{tab}" or t == tab:
            return True
    parts = (endpoint.path or "").split("/")
    if "companies" in parts:
        idx = parts.index("companies")
        if idx + 2 < len(parts):
            seg = parts[idx + 2]
            return _TAB_BY_PATH_SEGMENT.get(seg) == tab
    # Also try the module hint
    if endpoint.module and _TAB_BY_PATH_SEGMENT.get(endpoint.module) == tab:
        return True
    return False


def _substitute(path: str, subs: dict[str, str]) -> str:
    out = path
    for k, v in subs.items():
        out = out.replace("{" + k + "}", v)
    return out


def _derive_access_level(endpoint: CatalogEndpoint) -> str:
    if not endpoint.required_permission:
        return "authed"
    if endpoint.required_permission in {"owner", "admin"}:
        return "admin"
    return "authed"


def _build_catalog_endpoints(app) -> list[CatalogEndpoint]:
    """Lightweight re-introspect — same logic as /summary but inline."""
    out: list[CatalogEndpoint] = []
    for route in app.routes:
        if not hasattr(route, "methods") or not getattr(route, "path", None):
            continue
        for method in (m for m in (route.methods or []) if m not in {"HEAD", "OPTIONS"}):
            tags = list(getattr(route, "tags", None) or [])
            path = getattr(route, "path", "") or ""
            module = _module_from_tags_or_path(tags, path)
            try:
                perm = _extract_required_permission(route)
            except Exception:
                perm = None
            summary = getattr(route, "summary", None) or (getattr(route, "description", "") or "").split("\n", 1)[0][:200]
            out.append(CatalogEndpoint(
                path=path, method=method,
                operation_id=getattr(route, "operation_id", None) or getattr(route, "name", None),
                summary=summary,
                description=getattr(route, "description", None),
                tags=tags, module=module, required_permission=perm,
                deprecated=bool(getattr(route, "deprecated", False)),
            ))
    return out


def _available_tabs(endpoints: list[CatalogEndpoint]) -> list[str]:
    found: set[str] = set()
    for e in endpoints:
        for t in (e.tags or []):
            if t.startswith("tab."):
                found.add(t.split(".", 1)[1])
    found.update(set(_TAB_BY_PATH_SEGMENT.values()))
    return sorted(found)


@router.get("/by-company/{company_id}", response_model=CompanyCatalogResponse)
async def catalog_by_company(
    company_id: UUID,
    request: Request,
    tab: Optional[str] = Query(None, description="Filter by tab code (financials/kpi/loans/...)"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CompanyCatalogResponse:
    """Return endpoints applicable to a specific company with placeholders
    substituted. Optionally filtered to a single Detail-view tab."""
    co = (await db.execute(select(Company).where(Company.id == company_id))).scalar_one_or_none()
    if co is None:
        raise HTTPException(404, "Company not found")

    all_endpoints = _build_catalog_endpoints(request.app)
    company_scoped = [e for e in all_endpoints if _is_company_scoped(e)]

    if tab:
        company_scoped = [e for e in company_scoped if _endpoint_belongs_to_tab(e, tab)]

    co_id_str = str(company_id)
    subs = {"id": co_id_str, "company_id": co_id_str}
    if getattr(co, "code", None):
        subs["company_code"] = co.code

    substituted: list[CatalogEndpointWithSubstitution] = []
    for e in company_scoped:
        substituted.append(CatalogEndpointWithSubstitution(
            **e.model_dump(),
            display_path=_substitute(e.path, subs),
            substitutions=subs,
            access_level=_derive_access_level(e),
        ))

    return CompanyCatalogResponse(
        company_id=company_id,
        company_name=co.name_ru,
        endpoints=substituted,
        tabs=_available_tabs(all_endpoints),
        access_level="authed",
    )


# ─── Try-it-out endpoint ───────────────────────────────────────

_TRY_RESPONSE_MAX_BYTES = 64 * 1024
_DESTRUCTIVE_METHODS = {"POST", "PATCH", "PUT", "DELETE"}


@router.post("/try", response_model=TryResponse)
async def try_endpoint(
    body: TryRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> TryResponse:
    """Execute a catalog endpoint against own backend with the caller's
    session JWT. Destructive methods require `confirm_destructive=true`.
    Response body is capped to 64 KB."""
    import time, httpx

    path = body.path or "/"
    if not path.startswith("/"):
        path = "/" + path
    if path.startswith("/api/"):
        # Strip the public /api/ prefix — nginx adds it externally, but we go
        # directly to backend here.
        path = path[len("/api"):]
    if body.method in _DESTRUCTIVE_METHODS and not body.confirm_destructive:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"{body.method} is destructive — set confirm_destructive=true to proceed",
        )

    # Forward auth: prefer caller's original Authorization header
    headers = dict(body.headers or {})
    auth_hdr = request.headers.get("authorization")
    if auth_hdr and "Authorization" not in headers and "authorization" not in headers:
        headers["Authorization"] = auth_hdr
    headers.setdefault("Content-Type", "application/json")

    url = f"http://localhost:8000{path}"
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            resp = await client.request(
                body.method,
                url,
                headers=headers,
                json=body.body if body.body is not None else None,
            )
    except httpx.HTTPError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"try-it-out failed: {e}")

    duration_ms = int((time.perf_counter() - started) * 1000)
    raw = resp.content or b""
    truncated = len(raw) > _TRY_RESPONSE_MAX_BYTES
    body_text = raw[:_TRY_RESPONSE_MAX_BYTES].decode("utf-8", errors="replace") if raw else None

    return TryResponse(
        status_code=resp.status_code,
        headers=dict(resp.headers),
        body=body_text,
        duration_ms=duration_ms,
        truncated=truncated,
    )


# ─── Lightweight status endpoint for dev-docs hero ─────────────

@router.get("/status")
async def catalog_status(request: Request):
    """Public lightweight status — operational + version. No auth."""
    try:
        schema = request.app.openapi()
        version = schema.get("info", {}).get("version", "0.0.0")
        title = schema.get("info", {}).get("title", "UzAssets API")
    except Exception:
        version = "0.0.0"
        title = "UzAssets API"
    return {
        "operational": True,
        "title": title,
        "version": version,
    }
