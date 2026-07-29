from __future__ import annotations

import re

from bot.i18n import EN, RU, UZ, msg, normalize_locale


def _vars(value: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", value))


def test_bot_dictionaries_have_matching_keys_and_placeholders() -> None:
    assert RU.keys() == UZ.keys() == EN.keys()
    for key in RU:
        assert _vars(RU[key]) == _vars(UZ[key]) == _vars(EN[key])


def test_bot_locales_and_interpolation() -> None:
    assert normalize_locale("uz-Cyrl-UZ") == "uz-cyr"
    assert msg("total", "en", count=7) == "Total: <b>7</b>"
    assert "7" in msg("total", "uz-cyr", count=7)


def test_cyrillic_conversion_preserves_brands_and_markup() -> None:
    value = msg("test_notification", "uz-cyr")
    assert "UzAssets" in value
    assert msg("total", "uz-cyr", count=3).startswith("Жами:")
