"""CI-гейт классификации маршрутов модерации (Фаза 2 deny-by-default).

Статически (по AST, БЕЗ импорта приложения/БД) перечисляет ВСЕ state-changing
маршруты (@router.post/put/patch/delete) в app/api/routes/ и требует, чтобы
каждый был классифицирован в app/core/moderation_routes.ROUTE_CLASS.

Смысл: новый write-роут физически не пройдёт CI, пока его не отнесли к бакету
(A данные / B self-service / C система / D upload / N compute). Это и есть
«deny-by-default» на уровне процесса — забыть протриажить роут нельзя.

Тест самодостаточен (только stdlib + чистый модуль ROUTE_CLASS), поэтому не
требует testcontainers/БД.
"""
from __future__ import annotations

import ast
from pathlib import Path

from app.core.moderation_routes import ROUTE_CLASS

_WRITE = {"post", "put", "patch", "delete"}
_ROUTES_DIR = Path(__file__).resolve().parents[1] / "app" / "api" / "routes"


def _enumerate_write_routes() -> set[str]:
    """Ключи "<stem>:<func>:<METHOD>" всех write-эндпоинтов (AST-парсинг)."""
    keys: set[str] = set()
    for py in sorted(_ROUTES_DIR.glob("*.py")):
        if py.name == "__init__.py":
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"))
        # router-переменные с APIRouter (нужны только имена — префикс тут не важен)
        routers: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                fn = node.value.func
                nm = getattr(fn, "id", None) or getattr(fn, "attr", None)
                if nm == "APIRouter":
                    for t in node.targets:
                        if isinstance(t, ast.Name):
                            routers.add(t.id)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if (isinstance(dec, ast.Call)
                        and isinstance(dec.func, ast.Attribute)
                        and getattr(dec.func.value, "id", None) in routers
                        and dec.func.attr.lower() in _WRITE):
                    keys.add(f"{py.stem}:{node.name}:{dec.func.attr.upper()}")
    return keys


def test_every_write_route_is_classified():
    enumerated = _enumerate_write_routes()
    missing = sorted(enumerated - set(ROUTE_CLASS))
    assert not missing, (
        f"{len(missing)} write-роут(ов) НЕ классифицированы в "
        f"app/core/moderation_routes.ROUTE_CLASS — отнеси их к бакету "
        f"A/B/C/D/N:\n  " + "\n  ".join(missing)
    )


def test_no_stale_classification_entries():
    """Обратная сторона: в реестре нет записей для несуществующих маршрутов."""
    enumerated = _enumerate_write_routes()
    stale = sorted(set(ROUTE_CLASS) - enumerated)
    assert not stale, (
        f"{len(stale)} записей ROUTE_CLASS не соответствуют ни одному маршруту "
        f"(роут удалён/переименован?):\n  " + "\n  ".join(stale)
    )


def test_bucket_A_entries_have_module_and_action():
    bad = [
        k for k, rc in ROUTE_CLASS.items()
        if rc.bucket == "A" and (not rc.module or not rc.action)
    ]
    assert not bad, f"A-маршруты без module/action: {bad}"
