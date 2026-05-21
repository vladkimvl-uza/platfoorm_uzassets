"""UzAssets Platform · Python SDK (Phase 5.7).

Lightweight httpx wrapper. Generated types live in `types_generated.py`
after running `make sdk:python` (uses openapi-python-client under the hood).

Usage:
    from uzassets_sdk import UzAssetsClient

    sdk = UzAssetsClient(
        base_url="https://platform.uz-assets.uz/api",
        token="<your_jwt>",
    )
    companies = sdk.companies.list()
    detail    = sdk.companies.get("ngmk")
    ratings   = sdk.ratings.by_company(detail["id"])
"""
from __future__ import annotations

from typing import Any, Callable, Optional, Union

import httpx


__version__ = "0.1.0"


class UzAssetsApiError(Exception):
    def __init__(self, status_code: int, message: str, body: Any = None):
        super().__init__(f"[{status_code}] {message}")
        self.status_code = status_code
        self.message = message
        self.body = body


class UzAssetsClient:
    """Top-level SDK entry point. Each resource is exposed as an attribute."""

    DEFAULT_BASE = "https://platform.uz-assets.uz/api"

    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Union[str, Callable[[], Optional[str]], None] = None,
        timeout: float = 30.0,
        verify_ssl: bool = True,
    ):
        self.base_url = (base_url or self.DEFAULT_BASE).rstrip("/")
        self._token_provider: Callable[[], Optional[str]] = (
            token if callable(token) else (lambda: token)
        )
        self._client = httpx.Client(timeout=timeout, verify=verify_ssl)

        # Resource namespaces
        self.companies  = _CompaniesResource(self)
        self.library    = _LibraryResource(self)
        self.ratings    = _RatingsResource(self)
        self.financials = _FinancialsResource(self)
        self.catalog    = _CatalogResource(self)

    def request(self, method: str, path: str, *, json: Any = None,
                params: Optional[dict] = None) -> Any:
        url = f"{self.base_url}{'' if path.startswith('/') else '/'}{path}"
        headers = {"Accept": "application/json"}
        tok = self._token_provider()
        if tok:
            headers["Authorization"] = f"Bearer {tok}"

        resp = self._client.request(method, url, headers=headers, json=json, params=params)
        try:
            body = resp.json() if resp.content else None
        except Exception:
            body = resp.text

        if not resp.is_success:
            detail = body.get("detail") if isinstance(body, dict) else str(body or f"HTTP {resp.status_code}")
            raise UzAssetsApiError(resp.status_code, str(detail), body)

        return body

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "UzAssetsClient":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


# ── Resources ──────────────────────────────────────────────────────────

class _CompaniesResource:
    def __init__(self, c: UzAssetsClient): self._c = c
    def list(self) -> list[dict]:
        return self._c.request("GET", "/companies")
    def get(self, code_or_id: str) -> dict:
        return self._c.request("GET", f"/companies/{code_or_id}")


class _LibraryResource:
    def __init__(self, c: UzAssetsClient): self._c = c
    def list(self, sector: Optional[str] = None, search: Optional[str] = None,
             limit: int = 50, offset: int = 0) -> dict:
        params = {"limit": limit, "offset": offset}
        if sector: params["sector"] = sector
        if search: params["search"] = search
        return self._c.request("GET", "/library/companies", params=params)
    def detail(self, company_id: str) -> dict:
        return self._c.request("GET", f"/library/companies/{company_id}")
    def update_field(self, company_id: str, field_code: str, value: Any,
                     reason: Optional[str] = None) -> dict:
        return self._c.request("PATCH",
            f"/library/companies/{company_id}/fields/{field_code}",
            json={"value": value, "reason": reason})
    def fields(self) -> list[dict]:
        return self._c.request("GET", "/field-definitions")
    def tabs(self) -> list[dict]:
        return self._c.request("GET", "/library-tabs")


class _RatingsResource:
    def __init__(self, c: UzAssetsClient): self._c = c
    def by_company(self, code_or_id: str) -> dict:
        return self._c.request("GET", f"/companies/{code_or_id}/ratings")
    def list(self, **filters: Any) -> dict:
        return self._c.request("GET", "/ratings", params=filters)


class _FinancialsResource:
    def __init__(self, c: UzAssetsClient): self._c = c
    def list(self, **filters: Any) -> list[dict]:
        return self._c.request("GET", "/financials", params=filters)
    def get(self, report_id: str) -> dict:
        return self._c.request("GET", f"/financials/{report_id}")


class _CatalogResource:
    def __init__(self, c: UzAssetsClient): self._c = c
    def summary(self) -> dict:
        return self._c.request("GET", "/api-catalog/summary")
    def by_company(self, company_id: str, tab: Optional[str] = None) -> dict:
        params = {"tab": tab} if tab else None
        return self._c.request("GET", f"/api-catalog/by-company/{company_id}", params=params)
    def openapi(self) -> dict:
        return self._c.request("GET", "/api-catalog/openapi.json")
    def status(self) -> dict:
        return self._c.request("GET", "/api-catalog/status")


__all__ = ["UzAssetsClient", "UzAssetsApiError", "__version__"]
