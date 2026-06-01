"""Pure helpers for API Catalog (no DB, no Request)."""
from __future__ import annotations

from app.schemas.api_key import CatalogEndpoint

# Module → friendly group mapping
MODULE_GROUPS = {
    "auth": "Авторизация · доступ",        "rbac": "Авторизация · доступ",
    "companies": "Портфель",               "projects": "Портфель",
    "tasks": "Портфель",                   "boards": "Портфель",
    "comments": "Портфель",                "sectors": "Портфель",
    "financials": "Финансы",               "ratings": "Финансы",
    "dashboard": "Финансы",                "executive_dashboard": "Финансы",
    "finmodel_storage": "Финансы",         "business_plan": "Финансы",
    "credit_portfolio": "Инвестиции",      "invest_projects": "Инвестиции",
    "procurement_analysis": "Инвестиции",
    "notifications":     "Pack 11 · уведомления",
    "moderation":        "Pack 11 · уведомления",
    "admin_broadcasts":  "Pack 11 · уведомления",
    "broadcasts":        "Pack 11 · уведомления",
    "api_catalog":       "Pack 12 · API & Интеграции",
    "api_keys":          "Pack 12 · API & Интеграции",
    "service_accounts":  "Pack 12 · API & Интеграции",
}


TAB_BY_PATH_SEGMENT = {
    "financials":  "financials",
    "ratings":     "ratings",
    "kpi":         "kpi",
    "businessplan": "kpi",
    "bp":          "kpi",
    "credit-portfolio": "loans",
    "credits":     "loans",
    "loans":       "loans",
    "procurement": "procurement",
    "purchases":   "procurement",
    "forensic":    "procurement",
    "documents":   "documents",
    "shareholders": "identity",
    "esg":         "esg",
    "governance":  "governance",
    "consultants": "consultants",
    "notes":       "notes",
    "projects":    "projects",
    "tasks":       "tasks",
}


def extract_required_permission(route) -> str | None:
    """Recover the permission code from a `Depends(require_permission(code))`
    dependency by inspecting closure cells."""
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
        queue.extend(getattr(d, "dependencies", []) or [])
    return None


def module_from_tags_or_path(tags: list[str] | None, path: str) -> str:
    if tags:
        return tags[0].replace("-", "_").lower()
    seg = path.strip("/").split("/")[0] if path else ""
    return seg.replace("-", "_").lower()


def is_company_scoped(endpoint: CatalogEndpoint) -> bool:
    p = endpoint.path or ""
    if "{id}" in p or "{company_id}" in p or "{company_code}" in p:
        return True
    if endpoint.tags and any(t.startswith("company.") for t in endpoint.tags):
        return True
    return False


def endpoint_belongs_to_tab(endpoint: CatalogEndpoint, tab: str) -> bool:
    for t in (endpoint.tags or []):
        if t == f"tab.{tab}" or t == tab:
            return True
    parts = (endpoint.path or "").split("/")
    if "companies" in parts:
        idx = parts.index("companies")
        if idx + 2 < len(parts):
            seg = parts[idx + 2]
            return TAB_BY_PATH_SEGMENT.get(seg) == tab
    if endpoint.module and TAB_BY_PATH_SEGMENT.get(endpoint.module) == tab:
        return True
    return False


def substitute_path(path: str, subs: dict[str, str]) -> str:
    out = path
    for k, v in subs.items():
        out = out.replace("{" + k + "}", v)
    return out


def derive_access_level(endpoint: CatalogEndpoint) -> str:
    if not endpoint.required_permission:
        return "authed"
    if endpoint.required_permission in {"owner", "admin"}:
        return "admin"
    return "authed"


def build_catalog_endpoints(app) -> list[CatalogEndpoint]:
    """Lightweight introspection — same logic as /summary."""
    out: list[CatalogEndpoint] = []
    for route in app.routes:
        if not hasattr(route, "methods") or not getattr(route, "path", None):
            continue
        for method in (m for m in (route.methods or []) if m not in {"HEAD", "OPTIONS"}):
            tags = list(getattr(route, "tags", None) or [])
            path = getattr(route, "path", "") or ""
            module = module_from_tags_or_path(tags, path)
            try:
                perm = extract_required_permission(route)
            except Exception:
                perm = None
            summary = getattr(route, "summary", None) or (
                getattr(route, "description", "") or ""
            ).split("\n", 1)[0][:200]
            out.append(CatalogEndpoint(
                path=path, method=method,
                operation_id=getattr(route, "operation_id", None) or getattr(route, "name", None),
                summary=summary,
                description=getattr(route, "description", None),
                tags=tags, module=module, required_permission=perm,
                deprecated=bool(getattr(route, "deprecated", False)),
            ))
    return out


def available_tabs(endpoints: list[CatalogEndpoint]) -> list[str]:
    found: set[str] = set()
    for e in endpoints:
        for t in (e.tags or []):
            if t.startswith("tab."):
                found.add(t.split(".", 1)[1])
    found.update(set(TAB_BY_PATH_SEGMENT.values()))
    return sorted(found)
