"""Direction normalization — single source of truth.

Folds legacy free-text labels and case variants to a canonical code so the
chip filter, the count metric, and the moderation audit log always agree
on a single value per direction.

Use in task/project create + update endpoints:
    from app.core.direction_normalize import normalize_direction
    extra["direction"] = normalize_direction(payload.direction)
"""
from typing import Optional

# Canonical code → Russian label (mirrors frontend DIRS_META at
# CompanyBoardList.vue and InvestProjects DIRS). Adding a new direction
# requires updating BOTH sides + the seed in `directions` table.
_DIR_LABELS: dict[str, list[str]] = {
    "strategy":    ["Стратегическое управление"],
    "finance":     ["Финансы / риски / аудит", "Финансы", "Финансы/риски/аудит"],
    "procurement": ["Система закупок", "Закупки"],
    "orgdev":      ["Организационное развитие", "Орг. развитие"],
    "digital":     ["Цифровизация"],
    "operations":  ["Операционная эффективность", "Операционная"],
    "governance":  ["Корпоративное управление",
                    # Каталог переименован (июль 2026) — без этого алиаса
                    # свободный ввод нового имени не сворачивался в код и
                    # плодил дубли «корпоративное управлени…» в списках.
                    "Корпоративное управление и инвестиции"],
    "esg":         ["ESG"],
    "pr":          ["Связи с общественностью", "PR"],
    "pmo":         ["PMO"],
    "analytics":   ["Сводный отдел", "Аналитика"],
}

_LABEL_TO_CODE: dict[str, str] = {}
for _code, _labels in _DIR_LABELS.items():
    _LABEL_TO_CODE[_code.lower()] = _code  # code → code self-map
    for _lbl in _labels:
        _LABEL_TO_CODE[_lbl.lower().strip()] = _code

_VALID_CODES = set(_DIR_LABELS.keys())


def normalize_direction(raw: Optional[str]) -> Optional[str]:
    """Convert any direction value (code/label/free-text) → canonical code.

    Returns None for empty input. Returns the lowercased input if no
    canonical match found — preserves backwards compat for custom codes
    while still folding duplicates.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    low = s.lower()
    mapped = _LABEL_TO_CODE.get(low)
    if mapped:
        return mapped
    # Незнакомое значение: свернуть регистр (чтобы «Фыва»/«фыва» были одним
    # направлением), но показать по-человечески — с заглавной буквы. Раньше
    # возвращался голый lower(), и списки пестрели «корпоративное управлени…».
    return low[:1].upper() + low[1:]


def is_canonical_direction(code: str) -> bool:
    """True if `code` is one of the 11 canonical direction codes."""
    return code in _VALID_CODES
