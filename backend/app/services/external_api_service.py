"""External API service (Pack 12.2).

OpenAPI spec parsing + endpoint extraction. Pure functions — no DB access.
"""
from __future__ import annotations

from typing import Any


def validate_openapi(spec: dict) -> tuple[bool, str | None]:
    """Light validation. Returns (ok, error_message)."""
    if not isinstance(spec, dict):
        return False, "Spec must be a JSON object"
    if "openapi" not in spec and "swagger" not in spec:
        return False, "Missing 'openapi' or 'swagger' field — not a recognised spec"
    if "paths" not in spec or not isinstance(spec["paths"], dict):
        return False, "Missing 'paths' object"
    if "info" not in spec or not isinstance(spec["info"], dict):
        return False, "Missing 'info' object"
    return True, None


def extract_version(spec: dict) -> str:
    info = spec.get("info") or {}
    return str(info.get("version", "0.0.0"))


def extract_title(spec: dict) -> str:
    info = spec.get("info") or {}
    return str(info.get("title", "Untitled API"))


def count_endpoints(spec: dict) -> int:
    """Count operations (path+method pairs) excluding HEAD/OPTIONS/PARAMETERS placeholders."""
    if not isinstance(spec.get("paths"), dict):
        return 0
    n = 0
    methods = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}
    for _path, methods_obj in spec["paths"].items():
        if not isinstance(methods_obj, dict):
            continue
        for k in methods_obj.keys():
            if k.lower() in methods and k.lower() not in {"options", "head"}:
                n += 1
    return n


def list_endpoints(spec: dict) -> list[dict[str, Any]]:
    """Flatten the spec into a list of endpoint summaries (for browsing UI)."""
    if not isinstance(spec.get("paths"), dict):
        return []
    out: list[dict[str, Any]] = []
    methods = {"get", "post", "put", "patch", "delete", "trace"}
    for path, methods_obj in spec["paths"].items():
        if not isinstance(methods_obj, dict):
            continue
        for m, op in methods_obj.items():
            if not isinstance(op, dict):
                continue
            ml = m.lower()
            if ml not in methods:
                continue
            out.append({
                "path": path,
                "method": ml.upper(),
                "operation_id": op.get("operationId"),
                "summary":      op.get("summary"),
                "description":  op.get("description"),
                "tags":         list(op.get("tags") or []),
                "deprecated":   bool(op.get("deprecated", False)),
            })
    return out


def extract_servers(spec: dict) -> list[dict]:
    """OpenAPI 3.x servers; for 2.x return [host+basePath]."""
    if isinstance(spec.get("servers"), list):
        return [s for s in spec["servers"] if isinstance(s, dict)]
    if "host" in spec:
        scheme = (spec.get("schemes") or ["https"])[0]
        base = spec.get("basePath", "")
        return [{"url": f"{scheme}://{spec['host']}{base}"}]
    return []
