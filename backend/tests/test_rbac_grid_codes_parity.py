"""Паритет сетки «Доступ к модулям»: фронт испускает ровно то, что денайнит бэк.

Зачем этот тест. Сетка сохраняется как overlay: коды, попавшие в payload,
становятся grant, а коды из _GRID_MANAGEABLE_CODES, которых в payload нет,
становятся deny. Поэтому два множества обязаны совпадать:

  * лишнее на бэке  — сохранение сетки молча отбирает право, которое сетка
    даже не показывает (например, role-выданный reports.edit при
    заблокированном в UI уровне «Редактировать»);
  * недостающее на бэке — снятый уровень не снимает право, оно «залипает».

Тест не поднимает БД: сравнивает константы бэка с MODULE_REGISTRY фронта,
разобранным из исходника, — это единственный способ поймать расхождение,
которое иначе проявится только на живом пользователе.
"""
import re
from pathlib import Path

import pytest

from app.services.rbac_v3.service import (
    _GRID_CODE_LEVEL_ANCHOR,
    _GRID_MANAGEABLE_CODES,
    _GRID_MODULE_CODES,
)

_REGISTRY_TS = (
    Path(__file__).resolve().parents[2]
    / "frontend" / "src" / "composables" / "usePermissions.ts"
)

# MODULE_CODE_ALIASES на фронте: сетка показывает invest, права на investment.
_MODULE_CODE_ALIASES = {"invest": "investment"}
# READ_ALIASES в rbacV3.ts: старые роли несут ai.chat вместо ai.view.
_READ_ALIASES = {"ai.view": ["ai.chat"]}


def _parse_frontend_registry() -> dict[str, tuple[bool, bool, bool]]:
    """MODULE_REGISTRY фронта -> {канонический код модуля: (export, edit, import)}."""
    src = _REGISTRY_TS.read_text(encoding="utf-8")
    body = src.split("export const MODULE_REGISTRY = [")[1].split("] as const")[0]
    pattern = re.compile(
        r"code:\s*'([^']+)'.*?hasExport:\s*(true|false)"
        r".*?hasEdit:\s*(true|false).*?hasImport:\s*(true|false)",
        re.S,
    )
    out: dict[str, tuple[bool, bool, bool]] = {}
    for m in pattern.finditer(body):
        code = _MODULE_CODE_ALIASES.get(m.group(1), m.group(1))
        out[code] = (m.group(2) == "true", m.group(3) == "true", m.group(4) == "true")
    return out


def _frontend_managed_codes(flags: dict[str, tuple[bool, bool, bool]]) -> set[str]:
    """Повторяет levelsToPermissions по всем модулям и уровням + алиасы чтения."""
    codes: set[str] = set()
    for module, (has_export, has_edit, has_import) in flags.items():
        # уровень «Наблюдать»
        codes.add(f"{module}.view")
        if has_export:
            codes.add(f"{module}.export")
        # уровень «Редактировать» — надстройка над «Наблюдать»
        if has_edit:
            codes.add(f"{module}.edit")
        if has_import:
            codes.add(f"{module}.import")
    for code in list(codes):
        codes.update(_READ_ALIASES.get(code, []))
    return codes


@pytest.fixture(scope="module")
def frontend_flags() -> dict[str, tuple[bool, bool, bool]]:
    if not _REGISTRY_TS.exists():
        pytest.skip("исходники фронта недоступны (backend-only окружение)")
    flags = _parse_frontend_registry()
    assert flags, "не удалось разобрать MODULE_REGISTRY — изменился формат файла"
    return flags


def test_grid_modules_match_frontend_registry(frontend_flags):
    assert set(_GRID_MODULE_CODES) == set(frontend_flags)


def test_admin_module_is_not_grid_managed():
    """Администрирование выдаётся ролью: сетка не должна уметь ни выдать, ни отнять."""
    assert "admin" not in _GRID_MODULE_CODES
    assert not [c for c in _GRID_MANAGEABLE_CODES if c.split(".")[0] == "admin"]


def test_grid_never_manages_manage_suffix():
    """{module}.manage — уровень роли; deny на него отобрал бы доступ мимо сетки."""
    assert not [c for c in _GRID_MANAGEABLE_CODES if c.endswith(".manage")]


def test_manageable_codes_match_frontend_emission(frontend_flags):
    """Ядро проверки: множества совпадают ТОЧНО, в обе стороны."""
    frontend = _frontend_managed_codes(frontend_flags)
    backend = set(_GRID_MANAGEABLE_CODES)
    assert backend - frontend == set(), (
        "бэк денайнит коды, которых сетка не испускает — сохранение сетки "
        "отберёт права, выданные ролью"
    )
    assert frontend - backend == set(), (
        "сетка испускает коды, которых бэк не денайнит — снятие уровня "
        "оставит право «залипшим»"
    )


def test_every_managed_code_has_level_anchor_inside_the_set():
    """Якорь уровня обязан сам быть управляемым кодом, иначе deny не сойдётся."""
    for code, anchor in _GRID_CODE_LEVEL_ANCHOR.items():
        assert anchor in _GRID_MANAGEABLE_CODES, (code, anchor)
