"""Use cases for API Catalog."""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Optional
from uuid import UUID

import httpx
from fastapi import HTTPException
from fastapi import status as http_status

from app.schemas.api_key import (
    CatalogEndpoint,
    CatalogEndpointWithSubstitution,
    CatalogModule,
    CatalogSummary,
    CompanyCatalogResponse,
    ScopeItem,
    ScopeListResponse,
    TryRequest,
    TryResponse,
)
from app.services.api_catalog._helpers import (
    MODULE_GROUPS,
    available_tabs,
    build_catalog_endpoints,
    derive_access_level,
    endpoint_belongs_to_tab,
    extract_required_permission,
    is_company_scoped,
    module_from_tags_or_path,
    substitute_path,
)
from app.uow.ports import UnitOfWorkABC

log = logging.getLogger(__name__)

_TRY_RESPONSE_MAX_BYTES = 64 * 1024
_DESTRUCTIVE_METHODS = {"POST", "PATCH", "PUT", "DELETE"}


class ApiCatalogService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    # ─── summary ──────────────────────────────────────────────────

    def build_summary(self, app) -> CatalogSummary:
        try:
            schema = app.openapi()
        except Exception:
            log.exception("app.openapi() failed")
            schema = {"info": {"title": "UzAssets API", "version": "0.0.0"}}

        endpoints: list[CatalogEndpoint] = []
        module_counter: dict[str, int] = {}
        skipped = 0

        for route in app.routes:
            try:
                if not hasattr(route, "methods") or not getattr(route, "path", None):
                    # WebSocket route
                    if (hasattr(route, "path")
                            and getattr(route, "endpoint", None)
                            and getattr(route, "path", "").startswith("/")):
                        module = module_from_tags_or_path(None, route.path)
                        endpoints.append(CatalogEndpoint(
                            path=route.path,
                            method="WEBSOCKET",
                            operation_id=getattr(route, "name", None),
                            summary="WebSocket stream",
                            description=None, tags=[], module=module,
                            required_permission=None,
                        ))
                        module_counter[module] = module_counter.get(module, 0) + 1
                    continue

                for method in (m for m in (route.methods or [])
                               if m not in {"HEAD", "OPTIONS"}):
                    tags = list(getattr(route, "tags", None) or [])
                    path = getattr(route, "path", "") or ""
                    module = module_from_tags_or_path(tags, path)
                    try:
                        perm = extract_required_permission(route)
                    except Exception:
                        perm = None

                    summary = getattr(route, "summary", None)
                    description = getattr(route, "description", None)
                    if not summary and description:
                        summary = description.split("\n", 1)[0][:200]

                    endpoints.append(CatalogEndpoint(
                        path=path, method=method,
                        operation_id=getattr(route, "operation_id", None) or getattr(route, "name", None),
                        summary=summary, description=description,
                        tags=tags, module=module,
                        required_permission=perm,
                        deprecated=bool(getattr(route, "deprecated", False)),
                    ))
                    module_counter[module] = module_counter.get(module, 0) + 1
            except Exception as e:
                skipped += 1
                log.warning(
                    "Skipped route %s: %s: %s",
                    getattr(route, "path", "?"), type(e).__name__, e,
                )

        if skipped > 0:
            log.info("Catalog summary: skipped %s routes due to introspection errors", skipped)

        modules = [
            CatalogModule(
                name=m,
                group=MODULE_GROUPS.get(m, "Прочее"),
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

    # ─── openapi.enriched ─────────────────────────────────────────

    @staticmethod
    def build_enriched_openapi(app) -> dict:
        try:
            spec = json.loads(json.dumps(app.openapi()))  # deep copy
        except Exception:
            log.exception("openapi.enriched: app.openapi() failed")
            raise HTTPException(500, "OpenAPI spec generation failed; see backend logs")

        for route in app.routes:
            try:
                if not hasattr(route, "methods"):
                    continue
                perm = extract_required_permission(route)
                if not perm or route.path not in spec.get("paths", {}):
                    continue
                for method in (m.lower() for m in (route.methods or [])
                               if m not in {"HEAD", "OPTIONS"}):
                    op = spec["paths"][route.path].get(method)
                    if op is not None:
                        op["x-required-permission"] = perm
            except Exception as e:
                log.warning(
                    "openapi.enriched: skipped route %s: %s",
                    getattr(route, "path", "?"), e,
                )

        spec.setdefault("info", {})["x-platform"] = "UzAssets"
        return spec

    # ─── scopes ───────────────────────────────────────────────────

    async def list_scopes(self) -> ScopeListResponse:
        async with self.uow:
            rows = await self.uow.api_catalog.list_permissions()
        items = [
            ScopeItem(code=p.code, name=p.name, module=p.module, description=p.description)
            for p in rows
        ]
        grouped: dict[str, list[ScopeItem]] = {}
        for it in items:
            key = it.module or "general"
            grouped.setdefault(key, []).append(it)
        return ScopeListResponse(items=items, grouped_by_module=grouped)

    # ─── postman export ───────────────────────────────────────────

    @staticmethod
    def build_postman_collection(app) -> tuple[bytes, str]:
        """Returns (json_bytes, filename_slug)."""
        spec = app.openapi()
        info = spec.get("info", {})
        base_url = "{{baseUrl}}"

        collection: dict[str, Any] = {
            "info": {
                "name":         info.get("title", "UzAssets API"),
                "description":  info.get("description", "Auto-generated from OpenAPI."),
                "version":      info.get("version", "0.0.0"),
                "schema":       "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
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

        name_slug = re.sub(
            r"[^a-z0-9-]+", "-", info.get("title", "uzassets").lower(),
        )[:48].strip("-")
        return (
            json.dumps(collection, indent=2, ensure_ascii=False).encode("utf-8"),
            name_slug,
        )

    # ─── catalog by company ───────────────────────────────────────

    async def catalog_by_company(
        self,
        company_id: UUID,
        *,
        tab: Optional[str],
        app,
    ) -> CompanyCatalogResponse:
        async with self.uow:
            co = await self.uow.api_catalog.get_company(company_id)
            if co is None:
                raise HTTPException(404, "Company not found")
            co_code = getattr(co, "code", None)
            co_name = co.name_ru

        all_endpoints = build_catalog_endpoints(app)
        company_scoped = [e for e in all_endpoints if is_company_scoped(e)]
        if tab:
            company_scoped = [e for e in company_scoped if endpoint_belongs_to_tab(e, tab)]

        co_id_str = str(company_id)
        subs = {"id": co_id_str, "company_id": co_id_str}
        if co_code:
            subs["company_code"] = co_code

        substituted: list[CatalogEndpointWithSubstitution] = []
        for e in company_scoped:
            substituted.append(CatalogEndpointWithSubstitution(
                **e.model_dump(),
                display_path=substitute_path(e.path, subs),
                substitutions=subs,
                access_level=derive_access_level(e),
            ))

        return CompanyCatalogResponse(
            company_id=company_id,
            company_name=co_name,
            endpoints=substituted,
            tabs=available_tabs(all_endpoints),
            access_level="authed",
        )

    # ─── try-it-out ───────────────────────────────────────────────

    async def try_endpoint(
        self,
        body: TryRequest,
        *,
        forwarded_auth: Optional[str],
    ) -> TryResponse:
        path = body.path or "/"
        if not path.startswith("/"):
            path = "/" + path
        if path.startswith("/api/"):
            path = path[len("/api"):]
        if body.method in _DESTRUCTIVE_METHODS and not body.confirm_destructive:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                f"{body.method} is destructive — set confirm_destructive=true to proceed",
            )

        headers = dict(body.headers or {})
        if forwarded_auth and "Authorization" not in headers and "authorization" not in headers:
            headers["Authorization"] = forwarded_auth
        headers.setdefault("Content-Type", "application/json")

        url = f"http://localhost:8000{path}"
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
                resp = await client.request(
                    body.method, url,
                    headers=headers,
                    json=body.body if body.body is not None else None,
                )
        except httpx.HTTPError as e:
            raise HTTPException(http_status.HTTP_502_BAD_GATEWAY, f"try-it-out failed: {e}")

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

    # ─── status (public) ──────────────────────────────────────────

    @staticmethod
    def public_status(app) -> dict:
        try:
            schema = app.openapi()
            version = schema.get("info", {}).get("version", "0.0.0")
            title = schema.get("info", {}).get("title", "UzAssets API")
        except Exception:
            version = "0.0.0"
            title = "UzAssets API"
        return {"operational": True, "title": title, "version": version}
