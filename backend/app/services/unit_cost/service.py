"""Удельная себестоимость (Unit Cost per product).

Модель себестоимости продукции госкомпаний в разрезе продуктов:
  удельная себестоимость = энергозатраты + прочие статьи (на единицу продукции).

Данные (JSONB-снапшот в system_config, ключ raw_snapshot.unitCostData):
  • energyPrices — цены энергоносителей (редактируемо);
  • companies[code].products[] — продукты с:
      - energy{fuel: удельный расход} — ЗАПОЛНЕНО из отчёта энергоёмкости
        «1-илова» (электро кВт·ч/ед, газ м³/ед, жидкое т/ед); юзер правит;
      - components[] — прочие статьи себестоимости на единицу (юзер вводит);
      - output — годовой выпуск в натуре (юзер вводит; в платформе нет источника).

Стартовый seed (seed_data.json): каталог продуктов (веб-ресёрч ассортимента) +
энергонормы. Ленивая инициализация при первом чтении. Энергозатраты на единицу
= Σ(удельный расход × цена энергоносителя). «нет данных ≠ 0».
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.snapshot_store import SnapshotStore

_KEY = "raw_snapshot.unitCostData"
_SEED_PATH = Path(__file__).with_name("seed_data.json")

FUELS = ("electricity", "gas", "diesel", "mazut", "coal", "kerosene")
FUEL_LABELS = {
    "electricity": "Электроэнергия", "gas": "Природный газ", "diesel": "Дизель",
    "mazut": "Мазут", "coal": "Уголь", "kerosene": "Керосин",
}


def _load_seed() -> dict[str, Any]:
    try:
        return json.loads(_SEED_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"energyPrices": {}, "companies": {}}


# Эталонный период с реальными фактами из seed_data (энергоёмкость 2025).
# Все ПРОЧИЕ периоды засеваются пустым бланком (структура каталога без фактов),
# иначе новый год открывался бы копией фактов 2025 → «данные те же самые».
_SEED_PERIOD = "2025-annual"


def _blank_seed() -> dict[str, Any]:
    """Каталог для НОВОГО периода: сохраняем структуру продуктов (название,
    ед. изм., норму расхода и названия статей), но обнуляем ФАКТ — новый год
    начинается с чистого листа, а не копией эталонного 2025-annual.
    Рыночные ориентиры (energyPrices/world) остаются — это не данные компании."""
    seed = _load_seed()
    for _code, blk in (seed.get("companies", {}) or {}).items():
        for p in (blk.get("products") or []):
            p["energy"] = {}      # факт удельного расхода — пусто
            p["output"] = 0       # годовой выпуск — 0
            for c in (p.get("components") or []):
                c["value"] = 0    # прочие статьи (сум/ед.) — 0, названия сохраняем
        blk["imports"] = []
        blk["comments"] = []
    return seed


_SEED_NORMS: Optional[dict[str, dict[str, dict[str, Any]]]] = None


def _seed_norm_map() -> dict[str, dict[str, dict[str, Any]]]:
    """Каталожные нормы расхода {code: {product_name: {fuel: norm}}} (ленивый кэш).
    Для бэкфилла периодов, засеянных до появления поля `norm`."""
    global _SEED_NORMS
    if _SEED_NORMS is None:
        m: dict[str, dict[str, dict[str, Any]]] = {}
        for code, blk in (_load_seed().get("companies", {}) or {}).items():
            byname: dict[str, dict[str, Any]] = {}
            for p in (blk.get("products") or []):
                nm = str(p.get("name", "")).strip()
                if nm and p.get("norm"):
                    byname[nm] = p["norm"]
            if byname:
                m[code] = byname
        _SEED_NORMS = m
    return _SEED_NORMS


def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
        return f if f == f else None  # NaN-guard
    except (TypeError, ValueError):
        return None


_QUARTERS = ("annual", "q1", "q2", "q3", "q4")
_DEFAULT_WORLD = {"usd_rate": 12650, "brent": 70, "gold": 2600, "copper": 9500}


class UnitCostService:
    @staticmethod
    def _period_key(year: int, quarter: str) -> str:
        q = quarter if quarter in _QUARTERS else "annual"
        return f"{int(year)}-{q}"

    async def _read_raw(self, db: AsyncSession) -> dict[str, Any]:
        v = await SnapshotStore(db).load(_KEY)
        return v if isinstance(v, dict) else {}

    async def _write_raw(self, db: AsyncSession, data: dict[str, Any]) -> None:
        # P1 аудита: общий SnapshotStore + БЕЗ db.commit() — коммитом владеет
        # get_db на конце запроса (все роуты unit_cost на Depends(get_db)).
        # Раньше commit в СЕРВИСЕ нарушал 10-слойную архитектуру + сырой text()
        # дублировался с forensic/production.
        await SnapshotStore(db).save(
            _KEY, data,
            "Удельная себестоимость: цены/продукты по периодам (год+квартал)",
        )

    async def load_raw(self, db: AsyncSession) -> dict[str, Any]:
        """Весь снапшот; миграция старого ПЛОСКОГО формата → {periods:{...}}."""
        raw = await self._read_raw(db)
        if "periods" not in raw:
            if raw.get("companies"):  # старый плоский снапшот → период 2025-annual
                raw = {"periods": {"2025-annual": {
                    "energyPrices": raw.get("energyPrices", {}),
                    "world": raw.get("world", {}), "companies": raw.get("companies", {})}}}
            else:
                raw = {"periods": {}}
        raw.setdefault("periods", {})
        return raw

    def _period(self, raw: dict[str, Any], year: int, quarter: str) -> tuple[str, dict[str, Any], bool]:
        """Данные периода (при первом обращении сеются из каталога seed_data)."""
        key = self._period_key(year, quarter)
        per = raw["periods"].get(key)
        seeded = False
        if per is None:
            # эталон 2025-annual → реальные факты; прочие периоды → пустой бланк
            per = _load_seed() if key == _SEED_PERIOD else _blank_seed()
            raw["periods"][key] = per
            seeded = True
        elif key != _SEED_PERIOD and not per.get("_edited"):
            # период был авто-засеян ранее (persist-on-view до фикса), но НИКОГДА
            # не сохранялся вручную → показываем чистый бланк, а не устаревшую
            # копию фактов 2025. Реально отредактированные периоды (_edited) целы.
            per = _blank_seed()
            raw["periods"][key] = per
        per.setdefault("energyPrices", {})
        per.setdefault("companies", {})
        per.setdefault("world", dict(_DEFAULT_WORLD))
        self._backfill_norms(per)
        return key, per, seeded

    @staticmethod
    def _backfill_norms(per: dict[str, Any]) -> None:
        """Проставить каталожную норму продуктам, у которых её нет (периоды,
        засеянные до появления поля `norm`). Не трогает уже заданные нормы."""
        nm_map = _seed_norm_map()
        for code, block in (per.get("companies", {}) or {}).items():
            byname = nm_map.get(code)
            if not byname:
                continue
            for p in (block.get("products") or []):
                if not p.get("norm"):
                    seed_norm = byname.get(str(p.get("name", "")).strip())
                    if seed_norm:
                        p["norm"] = dict(seed_norm)

    async def available_periods(self, db: AsyncSession) -> list[str]:
        raw = await self.load_raw(db)
        return sorted(raw["periods"].keys())

    async def _fetch_world_live(self) -> dict[str, Any]:
        """Best-effort живой фид: USD/сум от ЦБ РУз, золото — публичный источник.
        Brent/медь — нет надёжного keyless-источника (остаются из кэша/ручные).
        Всё в try/except: капризный интернет VM не должен ронять overview."""
        out: dict[str, Any] = {}
        live: list[str] = []  # какие поля реально получены из живого источника
        try:
            import httpx
            async with httpx.AsyncClient(timeout=4.0, follow_redirects=True) as c:
                try:  # официальный курс USD Центрального банка Узбекистана
                    r = await c.get("https://cbu.uz/ru/arkhiv-kursov-valyut/json/")
                    for it in (r.json() or []):
                        if it.get("Ccy") == "USD":
                            out["usd_rate"] = round(float(it["Rate"]), 2)
                            live.append("usd_rate")
                            break
                except Exception:
                    pass
                try:  # спот-цена золота (USD/oz)
                    r = await c.get("https://data-asg.goldprice.org/dbXRates/USD",
                                    headers={"User-Agent": "Mozilla/5.0"})
                    xau = float(r.json()["items"][0]["xauPrice"])
                    if xau > 0:
                        out["gold"] = round(xau, 1)
                        live.append("gold")
                except Exception:
                    pass
        except Exception:
            pass
        # Brent/медь: надёжного keyless-источника нет → остаются ручными/дефолтными
        out["_live_fields"] = live
        return out

    async def _world_live(self, db: AsyncSession, raw: dict[str, Any]) -> dict[str, Any]:
        """Кэш живых цен (root-level, вне периодов): освежаем раз в час, best-effort."""
        wl = dict(raw.get("world_live") or {})
        stale = True
        ts = wl.get("updated_at")
        if ts:
            try:
                age = (datetime.now(UTC) - datetime.fromisoformat(ts)).total_seconds()
                stale = age > 3600
            except Exception:
                stale = True
        if stale:
            fetched = await self._fetch_world_live()
            live_fields = fetched.pop("_live_fields", []) if isinstance(fetched, dict) else []
            if fetched:
                wl = {**_DEFAULT_WORLD, **wl, **fetched,
                      "updated_at": datetime.now(UTC).isoformat(),
                      "source": "live" if live_fields else "default",
                      "live_fields": live_fields}
                raw["world_live"] = wl
                try:
                    await self._write_raw(db, raw)
                except Exception:
                    pass
        if not wl:
            wl = {**_DEFAULT_WORLD, "source": "default", "live_fields": []}
        wl.setdefault("live_fields", [])
        return wl

    # ─── Расчёт ──────────────────────────────────────────────────────
    @staticmethod
    def _price_map(prices: dict[str, Any], usd_rate: float) -> dict[str, float]:
        """Эффективная цена (сум): если задана цена в USD — пересчёт по курсу,
        иначе прямая цена в сумах. Так курс USD влияет на все привязанные цены."""
        out: dict[str, float] = {}
        for f in FUELS:
            pr = prices.get(f) or {}
            usd = _num(pr.get("usd"))
            if usd is not None and usd > 0 and usd_rate:
                out[f] = usd * usd_rate
            else:
                p = _num(pr.get("price"))
                if p is not None:
                    out[f] = p
        return out

    def _calc_product(self, p: dict[str, Any], pm: dict[str, float]) -> dict[str, Any]:
        energy = p.get("energy") or {}     # фактический удельный расход
        norm = p.get("norm") or {}         # норма расхода (плановый удельный)
        energy_cost = 0.0
        energy_breakdown: list[dict[str, Any]] = []
        overrun_unit = 0.0                 # сум/ед: (факт − норма)×цена, + перерасход / − экономия
        overrun_breakdown: list[dict[str, Any]] = []
        has_norm = False
        for f in FUELS:
            act = _num(energy.get(f))
            nrm = _num(norm.get(f))
            price = pm.get(f)
            if act is not None and price is not None:
                c = act * price
                energy_cost += c
                energy_breakdown.append({"fuel": f, "label": FUEL_LABELS[f],
                                         "norm": round(act, 4), "cost": round(c, 2)})
            # отклонение от нормы (нужны факт, норма и цена)
            if act is not None and nrm is not None:
                has_norm = True
                if price is not None:
                    delta = act - nrm
                    dcost = delta * price
                    overrun_unit += dcost
                    overrun_breakdown.append({
                        "fuel": f, "label": FUEL_LABELS[f],
                        "actual": round(act, 4), "norm_val": round(nrm, 4),
                        "delta": round(delta, 4), "cost": round(dcost, 2),
                    })
        comps = p.get("components") or []
        comp_out: list[dict[str, Any]] = []
        comp_cost = 0.0
        for c in comps:
            v = _num(c.get("value")) or 0.0
            comp_cost += v
            comp_out.append({"name": c.get("name", ""), "value": round(v, 2)})
        unit_cost = energy_cost + comp_cost
        output = _num(p.get("output")) or 0.0
        overrun_cost = round(overrun_unit * output, 2) if (output > 0 and has_norm) else None
        return {
            "name": p.get("name", ""), "unit": p.get("unit", ""),
            "output": round(output, 2),
            "energy_cost": round(energy_cost, 2),
            "components_cost": round(comp_cost, 2),
            "unit_cost": round(unit_cost, 2),
            "energy_share": (round(energy_cost / unit_cost * 100, 1) if unit_cost > 0 else None),
            "total_cost": round(unit_cost * output, 2) if output > 0 else None,
            "energy_breakdown": energy_breakdown,
            "energy": {f: _num(energy.get(f)) for f in FUELS if _num(energy.get(f)) is not None},
            "norm": {f: _num(norm.get(f)) for f in FUELS if _num(norm.get(f)) is not None},
            "components": comp_out,
            "has_energy": bool(energy_breakdown),
            "has_norm": has_norm,
            "overrun_unit": round(overrun_unit, 2) if has_norm else None,
            "overrun_cost": overrun_cost,
            "overrun_breakdown": overrun_breakdown,
        }

    async def overview(
        self, db: AsyncSession, *, year: int = 2025, quarter: str = "annual",
        scope_ids: Optional[Sequence[UUID]],
    ) -> dict[str, Any]:
        raw = await self.load_raw(db)
        key, per, _seeded = self._period(raw, year, quarter)
        # НЕ персистим при простом просмотре: незаполненные периоды считаются
        # свежим бланком каждый раз (детерминированно из seed). Запись — только
        # при явном сохранении (save_company/save_prices).
        world_live = await self._world_live(db, raw)
        world = per.get("world", {})
        usd_rate = _num(world.get("usd_rate")) or 0.0
        pm = self._price_map(per.get("energyPrices", {}), usd_rate)
        mix: dict[str, float] = {f: 0.0 for f in FUELS}

        # ростер компаний (имена/секторы/scope) из канона
        # include_in_rollups тянем, но НЕ фильтруем им ростер: компания вне свода
        # обязана оставаться отдельной строкой модуля — исключается только её вклад
        # в портфельные суммы ниже (иначе демо/непрофильная компания их искажает).
        q = text(
            "SELECT c.code, COALESCE(c.name_short, c.name_ru) AS name, c.id AS cid, "
            "       s.name_ru AS sector, s.color_hex AS color, c.include_in_rollups "
            "FROM companies c LEFT JOIN sectors s ON s.id = c.sector_id "
            "WHERE c.is_active = true AND c.code <> 'uzassets'"
        )
        rows = (await db.execute(q)).all()
        scope = {str(i) for i in scope_ids} if scope_ids is not None else None

        companies: list[dict[str, Any]] = []
        pf_total = 0.0
        pf_energy = 0.0
        pf_import = 0.0
        pf_overrun = 0.0
        pf_has_overrun = False
        prod_count = 0
        for code, name, cid, sector, color, in_rollups in rows:
            if scope is not None and str(cid) not in scope:
                continue
            block = (per.get("companies", {}) or {}).get(code, {})
            prods = [self._calc_product(p, pm) for p in (block.get("products") or [])]
            if in_rollups:
                prod_count += len(prods)
            c_total = sum(p["total_cost"] for p in prods if p["total_cost"] is not None)
            c_energy = sum(p["energy_cost"] * p["output"] for p in prods if p["output"])
            c_overrun = sum(p["overrun_cost"] for p in prods if p["overrun_cost"] is not None)
            c_has_overrun = any(p["overrun_cost"] is not None for p in prods)
            for p in prods:  # энергомикс по видам топлива (для донат-чарта)
                if p["output"] > 0 and in_rollups:
                    for eb in p["energy_breakdown"]:
                        mix[eb["fuel"]] += eb["cost"] * p["output"]
            # импорт (сырьё/комплектующие для производства), цена в USD → сум по курсу
            imports_out: list[dict[str, Any]] = []
            imp_cost = 0.0
            for it in (block.get("imports") or []):
                u = _num(it.get("usd")) or 0.0
                q = _num(it.get("qty")) or 0.0
                c = u * usd_rate * q
                imp_cost += c
                imports_out.append({"name": it.get("name", ""), "unit": it.get("unit", ""),
                                    "usd": round(u, 4), "qty": round(q, 2), "cost": round(c, 1)})
            if in_rollups:
                pf_total += c_total
                pf_energy += c_energy
                pf_import += imp_cost
                if c_has_overrun:
                    pf_overrun += c_overrun
                    pf_has_overrun = True
            filled = [p for p in prods if p["output"] > 0]
            companies.append({
                "code": code, "name": name, "sector": sector or "—",
                "in_rollups": bool(in_rollups),
                "color": color or "#94A3B8",
                "product_count": len(prods),
                "priced_count": len(filled),
                "total_cost": round(c_total, 1) if c_total else None,
                "energy_cost": round(c_energy, 1) if c_energy else None,
                "energy_share": (round(c_energy / c_total * 100, 1) if c_total > 0 else None),
                "import_cost": round(imp_cost, 1) if imp_cost else None,
                "overrun_cost": round(c_overrun, 1) if c_has_overrun else None,
                "imports": imports_out,
                "comments": block.get("comments") or [],
                "products": prods,
            })
        companies.sort(key=lambda x: (x["total_cost"] is None, -(x["total_cost"] or 0)))

        energy_mix = [
            {"fuel": f, "label": FUEL_LABELS[f], "cost": round(mix[f], 1),
             "share": round(mix[f] / pf_energy * 100, 1) if pf_energy > 0 else 0}
            for f in FUELS if mix[f] > 0
        ]
        energy_mix.sort(key=lambda x: -x["cost"])
        return {
            "year": int(year), "quarter": quarter, "period": key,
            "periods": sorted(raw["periods"].keys()),
            "energyPrices": per.get("energyPrices", {}),
            "world": world,
            "world_live": world_live,
            "fuel_labels": FUEL_LABELS,
            "companies": companies,
            "energy_mix": energy_mix,
            "portfolio": {
                "total_cost": round(pf_total, 1) if pf_total else None,
                "energy_cost": round(pf_energy, 1) if pf_energy else None,
                "components_cost": (round(pf_total - pf_energy, 1) if pf_total > 0 else None),
                "energy_share": (round(pf_energy / pf_total * 100, 1) if pf_total > 0 else None),
                "import_cost": round(pf_import, 1) if pf_import else None,
                "overrun_cost": round(pf_overrun, 1) if pf_has_overrun else None,
                # Счётчики портфеля — по тем же компаниям, что и суммы выше.
                "company_count": sum(1 for c in companies if c["in_rollups"]),
                "product_count": prod_count,
                "priced_count": sum(c["priced_count"] for c in companies if c["in_rollups"]),
            },
            "generated_at": datetime.now(UTC).isoformat(),
        }

    # ─── Правки ──────────────────────────────────────────────────────
    async def save_prices(
        self, db: AsyncSession, prices: dict[str, Any], world: dict[str, Any],
        *, year: int, quarter: str, user_email: str, user_id: Optional[str],
    ) -> dict[str, Any]:
        raw = await self.load_raw(db)
        key, data, _ = self._period(raw, year, quarter)
        clean: dict[str, Any] = dict(data.get("energyPrices", {}))
        for f in FUELS:
            src = prices.get(f)
            if not isinstance(src, dict):
                continue
            entry: dict[str, Any] = dict(clean.get(f, {}))
            entry["unit"] = src.get("unit") or entry.get("unit", "")
            p = _num(src.get("price"))
            if p is not None:
                if p < 0:
                    raise HTTPException(400, f"{FUEL_LABELS[f]}: цена — число ≥ 0")
                entry["price"] = p
            usd = _num(src.get("usd"))
            if usd is not None:
                if usd < 0:
                    raise HTTPException(400, f"{FUEL_LABELS[f]}: цена USD — число ≥ 0")
                entry["usd"] = usd
            elif "usd" in src:  # явный сброс привязки к USD
                entry.pop("usd", None)
            clean[f] = entry
        data["energyPrices"] = clean
        if isinstance(world, dict) and world:
            w = dict(data.get("world", {}))
            for k in ("usd_rate", "brent", "gold", "copper"):
                v = _num(world.get(k))
                if v is not None and v >= 0:
                    w[k] = v
            data["world"] = w
        data["_edited"] = True   # период реально отредактирован → не ре-бланкить
        await self._write_raw(db, raw)
        await self._audit(db, user_email, user_id, "unit_cost.prices.update", f"цены+мировые {key}")
        return {"energyPrices": clean, "world": data.get("world", {})}

    async def save_company(
        self, db: AsyncSession, code: str, products: list[dict[str, Any]],
        imports: list[dict[str, Any]], comments: list[dict[str, Any]],
        *, year: int, quarter: str, cid_in_scope: bool,
        user_email: str, user_id: Optional[str],
    ) -> dict[str, Any]:
        if not cid_in_scope:
            raise HTTPException(403, "Нет доступа к компании")
        raw = await self.load_raw(db)
        key, data, _ = self._period(raw, year, quarter)
        # комментарии: существующие (с at) сохраняем, новые (без at) штампуем
        clean_comments: list[dict[str, Any]] = []
        now_iso = datetime.now(UTC).isoformat()
        for c in (comments or []):
            txt = str(c.get("text", "")).strip()[:2000]
            if not txt:
                continue
            if c.get("at"):
                clean_comments.append({"author": str(c.get("author", ""))[:120],
                                       "text": txt, "at": str(c.get("at"))[:40],
                                       "mentions": [str(m)[:120] for m in (c.get("mentions") or [])][:20]})
            else:
                clean_comments.append({"author": user_email, "text": txt, "at": now_iso,
                                       "mentions": [str(m)[:120] for m in (c.get("mentions") or [])][:20]})
        clean_imports: list[dict[str, Any]] = []
        for it in (imports or []):
            nm = str(it.get("name", "")).strip()[:120]
            if not nm:
                continue
            clean_imports.append({
                "name": nm, "unit": str(it.get("unit", "")).strip()[:32],
                "usd": _num(it.get("usd")) or 0.0, "qty": _num(it.get("qty")) or 0.0,
            })
        clean_products: list[dict[str, Any]] = []
        for p in products:
            energy = {}
            norm = {}
            for f in FUELS:
                v = _num((p.get("energy") or {}).get(f))
                if v is not None:
                    energy[f] = v
                nv = _num((p.get("norm") or {}).get(f))
                if nv is not None:
                    norm[f] = nv
            comps = []
            for c in (p.get("components") or []):
                comps.append({"name": str(c.get("name", "")).strip()[:80],
                              "value": _num(c.get("value")) or 0.0})
            clean_products.append({
                "name": str(p.get("name", "")).strip()[:120],
                "unit": str(p.get("unit", "")).strip()[:32],
                "output": _num(p.get("output")) or 0.0,
                "energy": energy, "norm": norm, "components": comps,
            })
        data.setdefault("companies", {})[code] = {
            "products": clean_products, "imports": clean_imports, "comments": clean_comments,
        }
        data["_edited"] = True   # период реально отредактирован → не ре-бланкить
        await self._write_raw(db, raw)
        await self._audit(db, user_email, user_id, "unit_cost.company.update", f"{code} {key}")
        return {"code": code, "products": clean_products, "imports": clean_imports,
                "comments": clean_comments}

    async def _audit(self, db, email, uid, action, note) -> None:
        try:
            from app.core.audit_chain import append_audit_entry
            await append_audit_entry(
                db, actor_id=uid, actor_email=email, action=action,
                entity_type="system_config", entity_id=_KEY, notes=note,
            )
            await db.commit()
        except Exception:
            pass
