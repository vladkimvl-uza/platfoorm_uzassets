"""SOE Health Check — светофорная оценка здоровья компаний по методике МВФ.

Источник методики: IMF Fiscal Affairs Dept «SOE Health Check Tool»
(Downloads/SOE_HealthCheckTool.xlsm, настроен под Узбекистан) — 4-ступенчатые
пороги по коэффициентам → бенды риска 1..5 → Overall Rating (равные веса).

Данные — ТОЛЬКО канон financial_lines (summary FY, НСБУ/МСФО по выбору);
данные самого xlsm-файла не мигрируются (сверка июль-2026: 385 конфликтов
с редакторами — файл черновой; методика ценна, цифры — нет).

Честность (уроки аудитов):
  • нет данных ≠ 0: недоступный коэффициент = «н/д», исключён из Overall;
  • отрицательный капитал/EBITDA — отдельный кейс: бенд 5 с пометкой, без
    деления на отрицательное (иначе знак переворачивает смысл, ср. −187% в KPI);
  • Current/Quick Ratio СЧИТАЕМ: знаменатель текущих обязательств = stBorrowings
    («Краткосрочные обяз-ва» в схемах НСБУ/МСФО-редакторов); нет данных → «н/д»;
  • Cost Recovery и Cash Interest Coverage — приближения, помечены в формуле.
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# ─── Методика: коэффициенты и пороги МВФ (Parameters-лист) ────────────
# direction: gte — «больше = лучше» (value≥t1 → бенд 1) · lte — «меньше = лучше»
# thresholds: [t1, t2, t3, t4] → бенды 1..5
SOE_HEALTH_RATIOS: list[dict[str, Any]] = [
    {"key": "roa", "label": "ROA", "group": "Рентабельность",
     "formula": "Чистая прибыль / Активы",
     "direction": "gte", "thresholds": [0.10, 0.05, 0.0, -0.10], "fmt": "pct"},
    {"key": "roe", "label": "ROE", "group": "Рентабельность",
     "formula": "Чистая прибыль / Капитал",
     "direction": "gte", "thresholds": [0.20, 0.10, 0.0, -0.10], "fmt": "pct"},
    {"key": "costRecovery", "label": "Cost Recovery", "group": "Рентабельность",
     "formula": "Выручка / операционные затраты (≈ выручка − опер. прибыль)",
     "direction": "gte", "thresholds": [1.5, 1.3, 1.0, 0.8], "fmt": "x"},
    {"key": "currentRatio", "label": "Current Ratio", "group": "Ликвидность",
     "formula": "Оборотные активы / Краткосрочные обязательства",
     "direction": "gte", "thresholds": [2.0, 1.5, 1.3, 1.0], "fmt": "x"},
    {"key": "quickRatio", "label": "Quick Ratio", "group": "Ликвидность",
     "formula": "(Оборотные активы − Запасы) / Краткосрочные обязательства",
     "direction": "gte", "thresholds": [1.2, 1.0, 0.8, 0.7], "fmt": "x"},
    {"key": "debtorDays", "label": "Дебиторка, дни", "group": "Ликвидность",
     "formula": "Дебиторская задолженность / Выручка × 365",
     "direction": "lte", "thresholds": [30, 40, 50, 90], "fmt": "days"},
    {"key": "creditorDays", "label": "Кредиторка, дни", "group": "Ликвидность",
     "formula": "Кредиторская задолженность / Себестоимость × 365",
     "direction": "lte", "thresholds": [30, 60, 90, 120], "fmt": "days"},
    {"key": "debtToAssets", "label": "Долг/Активы", "group": "Платёжеспособность",
     "formula": "Долг / Активы",
     "direction": "lte", "thresholds": [0.3, 0.5, 0.8, 1.0], "fmt": "x"},
    {"key": "debtToEquity", "label": "Долг/Капитал", "group": "Платёжеспособность",
     "formula": "Долг / Капитал",
     "direction": "lte", "thresholds": [0.5, 1.0, 1.5, 2.0], "fmt": "x"},
    {"key": "debtToEbitda", "label": "Долг/EBITDA", "group": "Платёжеспособность",
     "formula": "Долг / EBITDA",
     "direction": "lte", "thresholds": [1.5, 2.0, 3.0, 5.0], "fmt": "x"},
    {"key": "interestCoverage", "label": "Interest Cov.", "group": "Платёжеспособность",
     "formula": "Операционная прибыль / Финансовые расходы",
     "direction": "gte", "thresholds": [2.0, 1.5, 1.2, 1.0], "fmt": "x"},
    {"key": "cashInterestCoverage", "label": "Cash Int. Cov.", "group": "Платёжеспособность",
     "formula": "EBITDA / Финансовые расходы (приближение)",
     "direction": "gte", "thresholds": [3.0, 2.0, 1.5, 1.0], "fmt": "x"},
    {"key": "debtCoverage", "label": "Debt Coverage", "group": "Платёжеспособность",
     "formula": "Операционный денежный поток (CFO) / Долг",
     "direction": "gte", "thresholds": [0.8, 0.6, 0.4, 0.3], "fmt": "x"},
    # Отношения с государством (лист Parameters, «Government Relationship»).
    # По умолчанию ВЫКЛЮЧЕН из Overall (информационный, как в инструменте) —
    # включается через редактор показателей.
    {"key": "govTransfersToRevenue", "label": "Трансферты/Выручка", "group": "Гос. поддержка",
     "formula": "Господдержка (трансферы) / Выручка",
     "direction": "lte", "thresholds": [0.3, 0.4, 0.5, 0.6], "fmt": "pct", "enabled": False},
]

SOE_HEALTH_ZONES = [
    {"max": 1.5, "key": "low",      "label": "Низкий риск",      "color": "#1D9E75"},
    {"max": 2.5, "key": "moderate", "label": "Умеренный",        "color": "#7DC4A0"},
    {"max": 3.5, "key": "elevated", "label": "Повышенный",       "color": "#EF9F27"},
    {"max": 4.5, "key": "high",     "label": "Высокий",          "color": "#E8590C"},
    {"max": 99,  "key": "severe",   "label": "Критический",      "color": "#E24B4A"},
]

_NEEDED_CODES = (
    "revenue", "cogs", "opProfit", "profit", "ebitda", "finCost",
    "totalAssets", "totalLiabilities", "equity", "debt",
    "accountsReceivable", "accountsPayable", "cfo",
    # CR/QR: totalCA + stBorrowings («Краткосрочные обяз-ва» = текущие
    # обязательства в схемах НСБУ/МСФО-редакторов) + inventories (МСФО)
    "totalCA", "stBorrowings", "inventories",
    # Altman Z-Score: retainedEarnings (сид из imf-healthcheck / редактор)
    "retainedEarnings",
    # Гос. поддержка: govGrants (трансферы) — для «Трансферты/Выручка»
    "govGrants",
)

# Выписка «Отчёт о фин. результатах» и «Баланс» для дрилла компании —
# упорядоченный набор канонических кодов (code, ярлык, итоговая-строка).
# Показываем только строки, где есть данные (иначе «нет данных ≠ 0»).
_IS_SPEC: list[tuple[str, str, bool]] = [
    ("revenue",      "Выручка",                     False),
    ("cogs",         "Себестоимость",               False),
    ("grossProfit",  "Валовая прибыль",             True),
    ("opProfit",     "Операционная прибыль (EBIT)", True),
    ("depreciation", "Амортизация (D&A)",           False),
    ("ebitda",       "EBITDA",                      True),
    ("finIncome",    "Финансовые доходы",           False),
    ("finCost",      "Финансовые расходы",          False),
    ("pbt",          "Прибыль до налога",           True),
    ("tax",          "Налог на прибыль",            False),
    ("profit",       "Чистая прибыль",              True),
    ("dividendsPaid", "Дивиденды выплаченные",      False),
]
_BS_SPEC: list[tuple[str, str, bool]] = [
    ("ppe",                "Основные средства",            False),
    ("totalNCA",           "Внеоборотные активы",          True),
    ("cash",               "Денежные средства",            False),
    ("accountsReceivable", "Дебиторская задолженность",    False),
    ("inventories",        "Запасы",                       False),
    ("totalCA",            "Оборотные активы",             True),
    ("totalAssets",        "ИТОГО Активы",                 True),
    ("equity",             "Собственный капитал",          True),
    ("shareCapital",       "  Уставный капитал",           False),
    ("retainedEarnings",   "  Нераспределённая прибыль",   False),
    ("ltBorrowings",       "Долгосрочные займы",           False),
    ("stBorrowings",       "Краткосрочные обязательства",  False),
    ("debt",               "Финансовый долг",              False),
    ("totalLiabilities",   "ИТОГО Обязательства",          True),
]

# Ключ порогов-оверрайдов в system_config (редактор показателей).
_PARAMS_KEY = "raw_snapshot.soeHealthParams"


def _band(value: float, direction: str, thr: list[float]) -> int:
    """Значение → бенд 1..5 по 4 порогам МВФ."""
    if direction == "gte":
        for i, t in enumerate(thr):
            if value >= t:
                return i + 1
        return 5
    for i, t in enumerate(thr):
        if value <= t:
            return i + 1
    return 5


def _zone(score: Optional[float]) -> Optional[dict]:
    if score is None:
        return None
    for z in SOE_HEALTH_ZONES:
        if score < z["max"]:
            return {"key": z["key"], "label": z["label"], "color": z["color"]}
    return None


def _z_score(m: dict[str, float]) -> Optional[dict[str, Any]]:
    """Altman Z''-Score (модель для развивающихся рынков / не-производств):
        Z'' = 6.56·X1 + 3.26·X2 + 6.72·X3 + 1.05·X4
        X1 = оборотный капитал / активы = (totalCA − stBorrowings)/totalAssets
        X2 = нераспр. прибыль / активы = retainedEarnings/totalAssets
        X3 = EBIT / активы = opProfit/totalAssets
        X4 = баланс. капитал / обязательства = equity/totalLiabilities
    Зоны: >2.6 устойчивая · 1.1–2.6 серая · <1.1 зона риска.
    БЕЗ EM-константы +3.25 — сверено 1:1 с эталонным Z инструмента SOE Health
    Check Tool (43/43 значения совпали). None, если нет входа («нет данных ≠ 0»)."""
    def g(k: str) -> Optional[float]:
        v = m.get(k)
        return float(v) if v is not None else None

    ta, tl = g("totalAssets"), g("totalLiabilities")
    ca, stb = g("totalCA"), g("stBorrowings")
    re, ebit, eq = g("retainedEarnings"), g("opProfit"), g("equity")
    if not ta or ta <= 0 or not tl or tl <= 0:
        return None
    if any(x is None for x in (ca, stb, re, ebit, eq)):
        return None
    wc = ca - stb
    z = round(6.56 * (wc / ta) + 3.26 * (re / ta)
              + 6.72 * (ebit / ta) + 1.05 * (eq / tl), 2)
    if z >= 2.6:
        zone = {"key": "safe", "label": "Устойчивая зона", "color": "#1D9E75"}
    elif z >= 1.1:
        zone = {"key": "grey", "label": "Серая зона", "color": "#EF9F27"}
    else:
        zone = {"key": "distress", "label": "Зона риска", "color": "#E24B4A"}
    return {"z": z, "zone": zone}


def _effective_ratios(overrides: dict) -> list[dict[str, Any]]:
    """Дефолтные пороги + оверрайды редактора показателей (system_config)."""
    out: list[dict[str, Any]] = []
    for r in SOE_HEALTH_RATIOS:
        rr = dict(r)
        rr["default_thresholds"] = list(r["thresholds"])
        rr["overridden"] = False
        # выбор индикатора (вкл/выкл в Overall) + вес (по умолч. 1.0)
        rr["enabled"] = bool(r.get("enabled", True))
        rr["weight"] = float(r.get("weight", 1.0))
        rr["default_enabled"] = rr["enabled"]
        rr["default_weight"] = rr["weight"]
        o = overrides.get(r["key"]) if isinstance(overrides, dict) else None
        if isinstance(o, dict):
            thr = o.get("thresholds")
            if isinstance(thr, list) and len(thr) == 4:
                try:
                    rr["thresholds"] = [float(x) for x in thr]
                    rr["overridden"] = True
                except (TypeError, ValueError):
                    pass
            if "enabled" in o:
                rr["enabled"] = bool(o["enabled"])
                rr["overridden"] = True
            if isinstance(o.get("weight"), (int, float)) and o["weight"] >= 0:
                rr["weight"] = float(o["weight"])
                rr["overridden"] = True
        out.append(rr)
    return out


def _compute_ratios(m: dict[str, float], ratios: Optional[list[dict[str, Any]]] = None) -> list[dict[str, Any]]:
    """Коэффициенты компании из канонических метрик. value=None → «н/д»;
    band может быть 5 при value=None (отриц. капитал/EBITDA) с note."""
    def g(k: str) -> Optional[float]:
        v = m.get(k)
        return float(v) if v is not None else None

    revenue, cogs = g("revenue"), g("cogs")
    op, profit, ebitda = g("opProfit"), g("profit"), g("ebitda")
    fin_cost = g("finCost")
    assets, equity, debt = g("totalAssets"), g("equity"), g("debt")
    ar, ap, cfo = g("accountsReceivable"), g("accountsPayable"), g("cfo")

    fc = abs(fin_cost) if fin_cost else None
    cogs_a = abs(cogs) if cogs else None
    out: dict[str, tuple[Optional[float], Optional[int], Optional[str]]] = {}

    out["roa"] = (profit / assets, None, None) if (profit is not None and assets and assets > 0) else (None, None, None)
    if equity is not None and equity <= 0:
        out["roe"] = (None, 5, "капитал ≤ 0")
        out["debtToEquity"] = (None, 5, "капитал ≤ 0")
    else:
        out["roe"] = (profit / equity, None, None) if (profit is not None and equity) else (None, None, None)
        out["debtToEquity"] = (debt / equity, None, None) if (debt is not None and equity) else (None, None, None)
    if revenue and op is not None and (revenue - op) > 0:
        out["costRecovery"] = (revenue / (revenue - op), None, None)
    else:
        out["costRecovery"] = (None, None, None)
    total_ca, st_liab, inv = g("totalCA"), g("stBorrowings"), g("inventories")
    if total_ca is not None and st_liab and st_liab > 0:
        out["currentRatio"] = (total_ca / st_liab, None, None)
        out["quickRatio"] = ((total_ca - abs(inv)) / st_liab, None, None) if inv is not None else (None, None, None)
    else:
        out["currentRatio"] = (None, None, None)
        out["quickRatio"] = (None, None, None)
    out["debtorDays"] = (abs(ar) / revenue * 365, None, None) if (ar is not None and revenue and revenue > 0) else (None, None, None)
    out["creditorDays"] = (abs(ap) / cogs_a * 365, None, None) if (ap is not None and cogs_a) else (None, None, None)
    out["debtToAssets"] = (debt / assets, None, None) if (debt is not None and assets and assets > 0) else (None, None, None)
    if ebitda is not None and ebitda <= 0:
        out["debtToEbitda"] = (None, 5, "EBITDA ≤ 0")
    else:
        out["debtToEbitda"] = (debt / ebitda, None, None) if (debt is not None and ebitda) else (None, None, None)
    out["interestCoverage"] = (op / fc, None, None) if (op is not None and fc) else (None, None, None)
    out["cashInterestCoverage"] = (ebitda / fc, None, None) if (ebitda is not None and fc) else (None, None, None)
    out["debtCoverage"] = (cfo / debt, None, None) if (cfo is not None and debt and debt > 0) else (None, None, None)
    gov = g("govGrants")
    out["govTransfersToRevenue"] = (abs(gov) / revenue, None, None) if (gov is not None and revenue and revenue > 0) else (None, None, None)

    rows: list[dict[str, Any]] = []
    for r in (ratios or SOE_HEALTH_RATIOS):
        value, forced_band, note = out.get(r["key"], (None, None, None))
        band = forced_band
        if band is None and value is not None:
            band = _band(value, r["direction"], r["thresholds"])
        rows.append({
            "key": r["key"], "label": r["label"], "group": r["group"],
            "formula": r["formula"], "direction": r["direction"],
            "thresholds": r["thresholds"], "fmt": r["fmt"],
            "value": (round(value, 4) if value is not None else None),
            "band": band, "note": note,
            "enabled": bool(r.get("enabled", True)), "weight": float(r.get("weight", 1.0)),
        })
    return rows


def _overall(rows: list[dict[str, Any]]) -> tuple[Optional[float], int]:
    """Взвешенное среднее бендов ВКЛЮЧЁННЫХ индикаторов (по умолчанию все веса
    1.0 → обычное среднее). Выключенные (enabled=False) и «н/д» — исключены."""
    sel = [(r["band"], float(r.get("weight", 1.0))) for r in rows
           if r["band"] is not None and r.get("enabled", True)]
    tw = sum(w for _, w in sel)
    if not sel or tw <= 0:
        return None, 0
    return round(sum(b * w for b, w in sel) / tw, 2), len(sel)


@dataclass
class SoeHealthService:
    # ─── Пороги: редактор показателей (оверрайды в system_config) ────
    async def load_params(self, db: AsyncSession) -> dict:
        res = await db.execute(
            text("SELECT value FROM system_config WHERE key = :k LIMIT 1"),
            {"k": _PARAMS_KEY},
        )
        row = res.first()
        if not row or not row[0]:
            return {}
        v = row[0]
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except json.JSONDecodeError:
                return {}
        return v if isinstance(v, dict) else {}

    async def save_params(
        self, db: AsyncSession, overrides: dict, *, user_email: str, user_id: Optional[str],
    ) -> list[dict[str, Any]]:
        """Сохранить оверрайды: пороги (опц., 4 числа + монотонность), выбор
        индикатора enabled (опц.), вес weight (опц., ≥0). Хранятся только
        отличия от дефолта. Аудит-запись обязательна."""
        meta = {r["key"]: r for r in SOE_HEALTH_RATIOS}
        clean: dict[str, dict] = {}
        for k, o in (overrides or {}).items():
            if k not in meta:
                raise HTTPException(400, f"Неизвестный коэффициент: {k}")
            if not isinstance(o, dict):
                continue
            entry: dict[str, Any] = {}
            # пороги (опционально)
            thr = o.get("thresholds")
            if thr is not None:
                if not isinstance(thr, list) or len(thr) != 4:
                    raise HTTPException(400, f"{meta[k]['label']}: нужно ровно 4 порога")
                try:
                    thr = [float(x) for x in thr]
                except (TypeError, ValueError):
                    raise HTTPException(400, f"{meta[k]['label']}: пороги должны быть числами")
                d = meta[k]["direction"]
                mono = all(thr[i] > thr[i + 1] for i in range(3)) if d == "gte" \
                    else all(thr[i] < thr[i + 1] for i in range(3))
                if not mono:
                    raise HTTPException(
                        400,
                        f"{meta[k]['label']}: пороги должны быть строго "
                        + ("убывающими (лучше ≥)" if d == "gte" else "возрастающими (лучше ≤)"),
                    )
                if thr != [float(x) for x in meta[k]["thresholds"]]:
                    entry["thresholds"] = thr
            # выбор индикатора (опционально)
            if "enabled" in o:
                en = bool(o["enabled"])
                if en != bool(meta[k].get("enabled", True)):
                    entry["enabled"] = en
            # вес (опционально, ≥0)
            if o.get("weight") is not None:
                try:
                    w = float(o["weight"])
                except (TypeError, ValueError):
                    raise HTTPException(400, f"{meta[k]['label']}: вес должен быть числом")
                if w < 0:
                    raise HTTPException(400, f"{meta[k]['label']}: вес не может быть отрицательным")
                if abs(w - float(meta[k].get("weight", 1.0))) > 1e-9:
                    entry["weight"] = w
            if entry:
                clean[k] = entry

        prev = await self.load_params(db)
        await db.execute(text(
            "INSERT INTO system_config (id, key, value, description, is_secret, created_at, updated_at) "
            "VALUES (gen_random_uuid(), :k, CAST(:v AS jsonb), :d, FALSE, NOW(), NOW()) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()"
        ), {
            "k": _PARAMS_KEY,
            "v": json.dumps(clean, ensure_ascii=False),
            "d": "SOE Health Check: оверрайды порогов риска (редактор показателей)",
        })
        await db.commit()
        # аудит: кто и что поменял (diff old→new)
        try:
            from app.core.audit_chain import append_audit_entry
            await append_audit_entry(
                db, actor_id=user_id, actor_email=user_email,
                action="soe_health.params.update",
                entity_type="system_config", entity_id=_PARAMS_KEY,
                diff={"old": prev, "new": clean},
                notes=f"пороги SOE Health Check: оверрайдов {len(clean)}",
            )
            await db.commit()
        except Exception:  # pragma: no cover — аудит не валит сохранение
            pass
        return _effective_ratios(clean)

    async def _load_metrics(
        self, db: AsyncSession, *, year: int, standard: str,
        scope_ids: Optional[Sequence[UUID]],
    ) -> dict[str, dict[str, Any]]:
        """{company_code: {name, sector..., metrics{lc: val}}} из канона (summary FY)."""
        # LEFT JOIN: в ростере ВСЕ активные компании — без отчётности за
        # год/стандарт показываются честными «н/д», а не исчезают из матрицы.
        sql = (
            "SELECT c.code, COALESCE(c.name_short, c.name_ru) AS name, c.id AS cid, "
            "       s.code AS sector_code, s.name_ru AS sector_name, s.color_hex AS sector_color, "
            "       c.legal_form AS legal_form, c.ownership_entity AS ownership_entity, "
            "       fl.line_code, fl.value "
            "FROM companies c "
            "LEFT JOIN sectors s ON s.id = c.sector_id "
            "LEFT JOIN financial_reports fr ON fr.company_id = c.id "
            "     AND fr.standard = :std AND fr.year = :yr "
            "     AND fr.is_detailed = false AND fr.quarter IS NULL "
            "LEFT JOIN financial_lines fl ON fl.report_id = fr.id "
            "     AND fl.line_code = ANY(:codes) AND fl.value IS NOT NULL "
            "WHERE c.is_active = true"
        )
        if scope_ids is None:
            # Флаг исключает компанию только из ПОРТФЕЛЬНЫХ цифр (средний балл,
            # зоны риска, %ВВП, разрезы по секторам). При явной области выборка
            # уже сужена вызывающим — иначе пользователь, чья область состоит из
            # такой компании, получит пустую матрицу здоровья.
            sql += " AND c.include_in_rollups = true"
        q = text(sql)
        rows = (await db.execute(q, {
            "std": standard, "yr": year, "codes": list(_NEEDED_CODES),
        })).all()
        out: dict[str, dict[str, Any]] = {}
        scope = {str(i) for i in scope_ids} if scope_ids is not None else None
        for code, name, cid, sec_code, sec_name, sec_color, legal_form, own_ent, lc, val in rows:
            if scope is not None and str(cid) not in scope:
                continue
            co = out.setdefault(code, {
                "code": code, "name": name, "company_id": str(cid),
                "sector_code": sec_code, "sector_name": sec_name,
                "sector_color": sec_color, "legal_form": legal_form,
                "ownership_entity": own_ent, "metrics": {},
            })
            if lc is not None and val is not None:
                co["metrics"][lc] = float(val)
        return out

    async def company_statement(
        self, db: AsyncSession, *, code: str, year: int, standard: str,
        scope_ids: Optional[Sequence[UUID]],
    ) -> dict[str, Any]:
        """Отчёт о фин. результатах + баланс одной компании (канон, summary FY)
        за год + предыдущий с Var(%). Ленивая подгрузка при открытии дрилла."""
        standard = "IFRS" if standard.upper() == "IFRS" else "NSBU"

        # 1) компания + scope-проверка
        crow = (await db.execute(text(
            "SELECT c.id, COALESCE(c.name_short, c.name_ru) AS name "
            "FROM companies c WHERE c.code = :code AND c.is_active = true"
        ), {"code": code})).first()
        if not crow:
            raise HTTPException(404, "Компания не найдена")
        cid, cname = crow
        if scope_ids is not None and cid not in set(scope_ids):
            raise HTTPException(403, "Нет доступа к компании")

        async def _lines(yr: int) -> dict[str, float]:
            rows = (await db.execute(text(
                "SELECT fl.line_code, fl.value "
                "FROM financial_reports fr "
                "JOIN financial_lines fl ON fl.report_id = fr.id "
                "WHERE fr.company_id = :cid AND fr.standard = :std AND fr.year = :yr "
                "AND fr.is_detailed = false AND fr.quarter IS NULL AND fl.value IS NOT NULL"
            ), {"cid": cid, "std": standard, "yr": yr})).all()
            return {lc: float(v) for lc, v in rows if v is not None}

        cur, prev = await _lines(year), await _lines(year - 1)

        def _rows(spec: list[tuple[str, str, bool]]) -> list[dict[str, Any]]:
            out: list[dict[str, Any]] = []
            for lc, label, total in spec:
                c, p = cur.get(lc), prev.get(lc)
                if c is None and p is None:
                    continue  # «нет данных ≠ 0» — не показываем пустую строку
                var = (round((c - p) / abs(p) * 100, 1)
                       if c is not None and p not in (None, 0) else None)
                out.append({
                    "code": lc, "label": label, "total": total,
                    "cur": (round(c, 1) if c is not None else None),
                    "prev": (round(p, 1) if p is not None else None),
                    "var_pct": var,
                })
            return out

        is_rows, bs_rows = _rows(_IS_SPEC), _rows(_BS_SPEC)
        return {
            "code": code, "name": cname, "standard": standard,
            "year": year, "prev_year": year - 1,
            "income_statement": is_rows, "balance_sheet": bs_rows,
            "has_data": bool(is_rows or bs_rows),
        }

    async def _load_series(
        self, db: AsyncSession, *, y0: int, y1: int, standard: str,
        scope_ids: Optional[Sequence[UUID]],
    ) -> dict[str, Any]:
        """Портфельные агрегаты по годам [y0..y1] (для трендов дашборда)."""
        base = (
            "SELECT fr.year, fl.line_code, SUM(fl.value) AS s "
            "FROM companies c "
            "JOIN financial_reports fr ON fr.company_id = c.id "
            "JOIN financial_lines fl ON fl.report_id = fr.id "
            "WHERE c.is_active = true AND fr.standard = :std "
            "AND fr.year BETWEEN :y0 AND :y1 "
            "AND fr.is_detailed = false AND fr.quarter IS NULL "
            "AND fl.line_code = ANY(:codes) AND fl.value IS NOT NULL "
        )
        params: dict[str, Any] = {
            "std": standard, "y0": y0, "y1": y1, "codes": list(_NEEDED_CODES),
        }
        if scope_ids is not None:
            base += "AND c.id = ANY(:scope) "
            params["scope"] = [str(i) for i in scope_ids]
        else:
            # Флаг исключает компанию только из ПОРТФЕЛЬНЫХ сумм и производных
            # коэффициентов (roa/roe/debtToEquity). При явной области выборка уже
            # сужена вызывающим — иначе тренды пользователя окажутся пустыми.
            base += "AND c.include_in_rollups = true "
        base += "GROUP BY fr.year, fl.line_code"
        rows = (await db.execute(text(base), params)).all()

        by_year: dict[int, dict[str, float]] = {}
        for yr, lc, s in rows:
            by_year.setdefault(int(yr), {})[lc] = float(s)

        years = list(range(y0, y1 + 1))
        def ratio(m: dict[str, float], num: str, den: str) -> Optional[float]:
            n, d = m.get(num), m.get(den)
            if n is None or not d or d <= 0:
                return None
            return round(n / d, 4)

        series = {
            "years": years,
            "totals": {k: [by_year.get(y, {}).get(k) for y in years]
                       for k in ("totalAssets", "totalLiabilities", "equity",
                                 "revenue", "ebitda", "profit", "debt")},
            "ratios": {
                "roa":          [ratio(by_year.get(y, {}), "profit", "totalAssets") for y in years],
                "roe":          [ratio(by_year.get(y, {}), "profit", "equity") for y in years],
                "debtToEquity": [ratio(by_year.get(y, {}), "debt", "equity") for y in years],
                "currentRatio": [ratio(by_year.get(y, {}), "totalCA", "stBorrowings") for y in years],
            },
        }
        return series

    async def build(
        self, db: AsyncSession, *, year: int, standard: str,
        scope_ids: Optional[Sequence[UUID]],
    ) -> dict[str, Any]:
        standard = "IFRS" if standard.upper() == "IFRS" else "NSBU"
        overrides = await self.load_params(db)
        ratios_eff = _effective_ratios(overrides)
        cur = await self._load_metrics(db, year=year, standard=standard, scope_ids=scope_ids)
        prev = await self._load_metrics(db, year=year - 1, standard=standard, scope_ids=scope_ids)

        companies: list[dict[str, Any]] = []
        for code, co in cur.items():
            rows = _compute_ratios(co["metrics"], ratios_eff)
            overall, n_avail = _overall(rows)
            prev_overall = None
            if code in prev:
                prev_overall, _n = _overall(_compute_ratios(prev[code]["metrics"], ratios_eff))
            m = co["metrics"]
            companies.append({
                "code": code, "name": co["name"], "company_id": co["company_id"],
                "sector_code": co["sector_code"], "sector_name": co["sector_name"],
                "sector_color": co["sector_color"],
                "ratios": rows, "overall": overall, "zone": _zone(overall),
                "prev_overall": prev_overall,
                "delta": (round(overall - prev_overall, 2)
                          if overall is not None and prev_overall is not None else None),
                "available": n_avail,
                # Altman Z''-Score (distress) — отдельно от RAG-Overall
                "z_score": _z_score(co["metrics"]),
                # сырьё для портфельных графиков (млрд сум)
                "metrics_out": {k: (round(m[k], 1) if k in m else None)
                                for k in ("totalLiabilities", "ebitda", "debt",
                                          "revenue", "totalAssets", "equity", "profit")},
            })
        # худшие сверху (внимание министра), н/д — в конец
        companies.sort(key=lambda x: (x["overall"] is None, -(x["overall"] or 0)))

        scored = [c for c in companies if c["overall"] is not None and c["available"] >= 5]
        zone_counts = {z["key"]: 0 for z in SOE_HEALTH_ZONES}
        for c in scored:
            zone_counts[c["zone"]["key"]] += 1
        portfolio_avg = round(sum(c["overall"] for c in scored) / len(scored), 2) if scored else None

        # total — в пределах scope пользователя (company-scoped видит «из своих»)
        # Знаменатель «X из N компаний» считаем по тому же набору, что и числитель
        # в _load_metrics: при явной области флаг не применяется (выборка уже сужена
        # вызывающим), при портфельном запросе демо/непрофильные исключаются.
        if scope_ids is not None:
            total_companies = (await db.execute(text(
                "SELECT count(*) FROM companies "
                "WHERE is_active = true AND id = ANY(:scope)"
            ), {"scope": [str(i) for i in scope_ids]})).scalar() or 0
        else:
            total_companies = (await db.execute(text(
                "SELECT count(*) FROM companies "
                "WHERE is_active = true AND include_in_rollups = true"
            ))).scalar() or 0

        series = await self._load_series(
            db, y0=year - 4, y1=year, standard=standard, scope_ids=scope_ids,
        )

        # ─── Фискальная материальность: %ВВП ───
        gdp_bln = (await db.execute(text(
            "SELECT gdp_bln FROM year_registry WHERE year = :y"
        ), {"y": year})).scalar()
        gdp_bln = float(gdp_bln) if gdp_bln else None
        totals_cur: dict[str, float] = {}
        for k in ("totalAssets", "totalLiabilities", "debt", "revenue"):
            s = sum(c["metrics_out"][k] for c in companies
                    if c["metrics_out"].get(k) is not None)
            totals_cur[k] = round(s, 1)
        pct_gdp = None
        if gdp_bln and gdp_bln > 0:
            pct_gdp = {k: round(v / gdp_bln * 100, 1) for k, v in totals_cur.items()}

        # ─── Разрезы по секторам (активы/обязательства/выручка/капитал) ───
        # суммируем метрики компаний по сектору; «нет данных ≠ 0» (пропуски не
        # тянут сумму вниз, но и не выдаём отсутствие за ноль — считаем только
        # присутствующие значения).
        _sec: dict[str, dict[str, Any]] = {}
        for c in companies:
            sc = c["sector_code"] or "other"
            s = _sec.setdefault(sc, {
                "code": sc, "name": c["sector_name"] or "Прочее",
                "color": c["sector_color"] or "#94A3B8",
                "totalAssets": 0.0, "totalLiabilities": 0.0,
                "revenue": 0.0, "equity": 0.0, "profit": 0.0, "count": 0,
            })
            s["count"] += 1
            for k in ("totalAssets", "totalLiabilities", "revenue", "equity", "profit"):
                v = c["metrics_out"].get(k)
                if v is not None:
                    s[k] += v
        by_sector = sorted(
            _sec.values(), key=lambda x: x["totalLiabilities"], reverse=True,
        )
        for s in by_sector:
            for k in ("totalAssets", "totalLiabilities", "revenue", "equity", "profit"):
                s[k] = round(s[k], 1)
            # рентабельность сектора (ratio-of-sums; None при неположит. базе)
            s["roa"] = (round(s["profit"] / s["totalAssets"], 4)
                        if s["totalAssets"] > 0 else None)
            s["roe"] = (round(s["profit"] / s["equity"], 4)
                        if s["equity"] > 0 else None)

        # ─── Прибыльные / убыточные (по знаку чистой прибыли) ───
        prof = loss = unknown = 0
        for c in companies:
            p = c["metrics_out"].get("profit")
            if p is None:
                unknown += 1
            elif p >= 0:
                prof += 1
            else:
                loss += 1

        # ─── Орг-правовая форма (пай Legal Form) ───
        _lf: dict[str, int] = {}
        for c in companies:
            lf = (c.get("legal_form") or "").strip() or "Не указана"
            _lf[lf] = _lf.get(lf, 0) + 1
        legal_form_split = sorted(
            ({"label": k, "count": v} for k, v in _lf.items()),
            key=lambda x: x["count"], reverse=True,
        )

        # ─── Орган управления / собственник (пай Ownership entity) ───
        _own: dict[str, int] = {}
        for c in companies:
            oe = (c.get("ownership_entity") or "").strip() or "Не указан"
            _own[oe] = _own.get(oe, 0) + 1
        ownership_split = sorted(
            ({"label": k, "count": v} for k, v in _own.items()),
            key=lambda x: x["count"], reverse=True,
        )

        return {
            "series": series,
            "year": year,
            "standard": standard,
            "ratios_meta": ratios_eff,
            "params_overridden": bool(overrides),
            "zones": SOE_HEALTH_ZONES,
            "companies": companies,
            "portfolio": {
                "avg": portfolio_avg,
                "zone": _zone(portfolio_avg),
                "zone_counts": zone_counts,
                "scored_count": len(scored),
                "total_companies": total_companies,
                "worst": ([{"code": c["code"], "name": c["name"], "overall": c["overall"]}
                           for c in scored[:3]] if scored else []),
                "best": ([{"code": c["code"], "name": c["name"], "overall": c["overall"]}
                          for c in sorted(scored, key=lambda x: x["overall"])[:3]] if scored else []),
                "by_sector": by_sector,
                "profit_split": {"profitable": prof, "loss": loss, "unknown": unknown},
                "legal_form_split": legal_form_split,
                "ownership_split": ownership_split,
                "gdp_bln": gdp_bln,
                "totals": totals_cur,
                "pct_gdp": pct_gdp,
            },
            # без брендинга источника в UI (пожелание пользователя) — методика
            # описана нейтрально; провенанс порогов см. в докстринге модуля.
            "methodology": "SOE Health Check Tool · RAG-оценка финансовой устойчивости, пороги настраиваемые",
            "generated_at": datetime.now(UTC).isoformat(),
        }
