"""Ядро локализации бэкенда — зеркало фронтового src/locale/i18n.ts.

Принципы (одинаковые на обоих концах платформы):
- КЛЮЧ — русская строка как написана в коде: ``tr("Файл не найден", loc)``.
  Нет перевода → возвращается русский текст (ничего не ломается).
- Словари лежат в ``app/locale_dict/*.py`` и обнаруживаются автоматически
  (pkgutil) — модули добавляются независимо, без общего реестра.
  Каждый модуль словаря экспортирует:
      UZ  — ru → узбекская ЛАТИНИЦА (обязательный);
      EN  — ru → английский (обязательный);
      CYR — ru → узбекская КИРИЛЛИЦА, только исключения (по умолчанию
            кириллица генерируется транслитерацией латиницы).
- Плейсхолдеры ``{var}`` переживают перевод: ``tr("Строк: {n}", loc, n=5)``.

Локаль запроса:
- фронт шлёт заголовок ``X-UI-Locale`` (ru | uz-latn | uz-cyr | en) на каждый
  запрос → ``locale_from_request(request)``;
- для офлайн-каналов (email/Telegram/дайджесты) язык берётся из
  ``users.ui_locale`` (см. runtime-миграцию) → ``locale_of_user(user)``.
"""
from __future__ import annotations

import importlib
import pkgutil
import re
from typing import Any, Optional

VALID_LOCALES = ("ru", "uz-latn", "uz-cyr", "en")
DEFAULT_LOCALE = "ru"

# ── Транслитерация uz-latn → uz-cyr (порт frontend/src/locale/translit.ts) ──

_ACRONYM_RE = re.compile(r"^[A-Z0-9.\-+/%№]{2,}$")
_ROMAN_RE = re.compile(r"^[IVX]$")  # одиночные римские цифры (I chorak)
_WORD_RE = re.compile(r"[A-Za-zʻʼ'`’]+")
_PLACEHOLDER_SPLIT = re.compile(r"(\{\w+\})")

_DIGRAPHS: list[tuple[re.Pattern[str], str]] = [
    # -tsiya/-tsion → ция/цион (generatsiya, operatsion — заимствования)
    (re.compile(r"tsiya"), "ция"), (re.compile(r"Tsiya"), "Ция"), (re.compile(r"TSIYA"), "ЦИЯ"),
    (re.compile(r"tsion"), "цион"), (re.compile(r"Tsion"), "Цион"), (re.compile(r"TSION"), "ЦИОН"),
    (re.compile(r"O[ʻ'`’ʼ]"), "Ў"), (re.compile(r"o[ʻ'`’ʼ]"), "ў"),
    (re.compile(r"G[ʻ'`’ʼ]"), "Ғ"), (re.compile(r"g[ʻ'`’ʼ]"), "ғ"),
    (re.compile(r"SH"), "Ш"), (re.compile(r"Sh"), "Ш"), (re.compile(r"sh"), "ш"),
    (re.compile(r"CH"), "Ч"), (re.compile(r"Ch"), "Ч"), (re.compile(r"ch"), "ч"),
    (re.compile(r"YO"), "Ё"), (re.compile(r"Yo"), "Ё"), (re.compile(r"yo"), "ё"),
    (re.compile(r"YA"), "Я"), (re.compile(r"Ya"), "Я"), (re.compile(r"ya"), "я"),
    (re.compile(r"YU"), "Ю"), (re.compile(r"Yu"), "Ю"), (re.compile(r"yu"), "ю"),
    (re.compile(r"YE"), "Е"), (re.compile(r"Ye"), "Е"), (re.compile(r"ye"), "е"),
]

_SINGLES = str.maketrans({
    "a": "а", "b": "б", "c": "с", "d": "д", "e": "е", "f": "ф", "g": "г",
    "h": "ҳ", "i": "и", "j": "ж", "k": "к", "l": "л", "m": "м", "n": "н",
    "o": "о", "p": "п", "q": "қ", "r": "р", "s": "с", "t": "т", "u": "у",
    "v": "в", "x": "х", "y": "й", "z": "з",
    "A": "А", "B": "Б", "C": "С", "D": "Д", "E": "Е", "F": "Ф", "G": "Г",
    "H": "Ҳ", "I": "И", "J": "Ж", "K": "К", "L": "Л", "M": "М", "N": "Н",
    "O": "О", "P": "П", "Q": "Қ", "R": "Р", "S": "С", "T": "Т", "U": "У",
    "V": "В", "X": "Х", "Y": "Й", "Z": "З",
    "ʻ": "ъ", "ʼ": "ъ", "'": "ъ", "`": "ъ", "’": "ъ",
})


def _translit_word(w: str) -> str:
    if _ACRONYM_RE.match(w) or _ROMAN_RE.match(w):
        return w  # KPI, IFRS, FY-2026, римские I/V/X — остаются латиницей
    s = w
    for pat, sub in _DIGRAPHS:
        s = pat.sub(sub, s)
    if s[:1] == "E":
        s = "Э" + s[1:]
    elif s[:1] == "e":
        s = "э" + s[1:]
    return s.translate(_SINGLES)


def translit_latin_to_cyrillic(text: str) -> str:
    """uz-latn → uz-cyr; {placeholders} и акронимы не транслитерируются."""
    parts = _PLACEHOLDER_SPLIT.split(text)
    out: list[str] = []
    for part in parts:
        if part.startswith("{"):
            out.append(part)
        else:
            out.append(_WORD_RE.sub(lambda m: _translit_word(m.group(0)), part))
    return "".join(out)


# ── Словари (автообнаружение app/locale_dict/*) ─────────────────────────

_UZ: dict[str, str] = {}
_EN: dict[str, str] = {}
_CYR: dict[str, str] = {}
_loaded = False


def _load_dicts() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        import app.locale_dict as pkg
    except ImportError:
        return
    for m in pkgutil.iter_modules(pkg.__path__):
        try:
            mod = importlib.import_module(f"app.locale_dict.{m.name}")
        except Exception:  # noqa: S112 — битый словарь не должен ронять API
            continue
        _UZ.update(getattr(mod, "UZ", {}) or {})
        _EN.update(getattr(mod, "EN", {}) or {})
        _CYR.update(getattr(mod, "CYR", {}) or {})


_cyr_cache: dict[str, str] = {}


def normalize_locale(raw: Optional[str]) -> str:
    v = (raw or "").strip().lower()
    return v if v in VALID_LOCALES else DEFAULT_LOCALE


def tr(ru: str, locale: Optional[str], **vars: Any) -> str:
    """Перевод пользовательской строки. Ключ — русский текст."""
    _load_dicts()
    loc = normalize_locale(locale)
    out = ru
    if loc == "uz-latn":
        out = _UZ.get(ru, ru)
    elif loc == "uz-cyr":
        override = _CYR.get(ru)
        if override is not None:
            out = override
        else:
            lat = _UZ.get(ru)
            if lat is not None:
                cached = _cyr_cache.get(lat)
                if cached is None:
                    cached = translit_latin_to_cyrillic(lat)
                    _cyr_cache[lat] = cached
                out = cached
    elif loc == "en":
        out = _EN.get(ru, ru)
    if vars:
        try:
            out = out.format(**vars)
        except (KeyError, IndexError, ValueError):
            pass  # битый плейсхолдер в словаре — показываем как есть
    return out


# ── Локаль запроса/пользователя ─────────────────────────────────────────

def locale_from_request(request: Any) -> str:
    """Заголовок X-UI-Locale (шлётся фронтом на каждый запрос)."""
    try:
        return normalize_locale(request.headers.get("X-UI-Locale"))
    except Exception:
        return DEFAULT_LOCALE


def locale_of_user(user: Any) -> str:
    """users.ui_locale — для офлайн-каналов (email/Telegram/дайджесты)."""
    return normalize_locale(getattr(user, "ui_locale", None))
