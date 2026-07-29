"""Request-scoped backend localization and AI-language contract."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import HTTPException, Request

from app.core.error_handlers import http_exception_handler
from app.core.i18n import (
    ai_language_instruction,
    current_locale,
    pop_locale,
    push_locale,
    tr,
)
from app.services.audit_field_labels import field_label
from scripts.i18n_audit import _dictionary_integrity


def _request(locale: str) -> Request:
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/test",
        "headers": [(b"x-ui-locale", locale.encode())],
    })


@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        ("ru", "Компания не найдена"),
        ("uz-latn", "Kompaniya topilmadi"),
        ("uz-cyr", "Компания топилмади"),
        ("en", "Company not found"),
    ],
)
def test_backend_dictionary_all_locales(locale: str, expected: str) -> None:
    assert tr("Компания не найдена", locale) == expected


@pytest.mark.asyncio
async def test_http_exception_uses_ui_locale_header() -> None:
    response = await http_exception_handler(
        _request("en"), HTTPException(status_code=404, detail="Компания не найдена"),
    )
    assert response.status_code == 404
    assert json.loads(response.body)["detail"] == "Company not found"


def test_locale_context_controls_ai_response_language() -> None:
    token = push_locale("uz-cyr")
    try:
        assert current_locale() == "uz-cyr"
        instruction = ai_language_instruction()
        assert "uz-cyr" in instruction
        assert "ў, ғ, қ, ҳ" in instruction
    finally:
        pop_locale(token)
    assert current_locale() == "ru"


def test_unknown_locale_is_fail_safe_russian() -> None:
    token = push_locale("xx")
    try:
        assert current_locale() == "ru"
    finally:
        pop_locale(token)


def test_dynamic_translation_preserves_database_values() -> None:
    assert tr(
        "Компания «{company}» не найдена",
        "en",
        company="План",
    ) == "Company “План” was not found"


def test_audit_field_labels_follow_request_locale() -> None:
    token = push_locale("en")
    try:
        assert field_label("scope_companies") == "Accessible companies"
        assert field_label("unknown_custom_field") == "Unknown custom field"
    finally:
        pop_locale(token)


def test_backend_dictionary_integrity() -> None:
    locale_dir = Path(__file__).resolve().parents[1] / "app" / "locale_dict"
    assert _dictionary_integrity(locale_dir) == []
