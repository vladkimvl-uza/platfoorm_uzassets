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


def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
        return f if f == f else None  # NaN-guard
    except (TypeError, ValueError):
        return None


class UnitCostService:
    async def _read(self, db: AsyncSession) -> dict[str, Any]:
        row = (await db.execute(
            text("SELECT value FROM system_config WHERE key = :k LIMIT 1"), {"k": _KEY},
        )).first()
        if not row or not row[0]:
            return {}
        v = row[0]
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except json.JSONDecodeError:
                return {}
        return v if isinstance(v, dict) else {}

    async def _write(self, db: AsyncSession, data: dict[str, Any]) -> None:
        await db.execute(text(
            "INSERT INTO system_config (id, key, value, description, is_secret, created_at, updated_at) "
            "VALUES (gen_random_uuid(), :k, CAST(:v AS jsonb), :d, FALSE, NOW(), NOW()) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()"
        ), {"k": _KEY, "v": json.dumps(data, ensure_ascii=False),
            "d": "Удельная себестоимость: цены энергоносителей + продукты компаний"})
        await db.commit()

    async def load(self, db: AsyncSession) -> dict[str, Any]:
        """Снапшот; при первом чтении инициализируется seed'ом (энергонормы+каталог)."""
        data = await self._read(db)
        if not data or not data.get("companies"):
            data = _load_seed()
            try:
                await self._write(db, data)
            except Exception:
                pass  # чтение не должно падать из-за записи
        data.setdefault("energyPrices", {})
        data.setdefault("companies", {})
        # мировые ориентиры + курс (влияют на цены, привязанные к USD)
        data.setdefault("world", {"usd_rate": 12650, "brent": 70, "gold": 2600, "copper": 9500})
        return data

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
        energy = p.get("energy") or {}
        energy_cost = 0.0
        energy_breakdown: list[dict[str, Any]] = []
        for f in FUELS:
            norm = _num(energy.get(f))
            if norm is None or f not in pm:
                continue
            c = norm * pm[f]
            energy_cost += c
            energy_breakdown.append({"fuel": f, "label": FUEL_LABELS[f],
                                     "norm": round(norm, 4), "cost": round(c, 2)})
        comps = p.get("components") or []
        comp_out: list[dict[str, Any]] = []
        comp_cost = 0.0
        for c in comps:
            v = _num(c.get("value")) or 0.0
            comp_cost += v
            comp_out.append({"name": c.get("name", ""), "value": round(v, 2)})
        unit_cost = energy_cost + comp_cost
        output = _num(p.get("output")) or 0.0
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
            "components": comp_out,
            "has_energy": bool(energy_breakdown),
        }

    async def overview(
        self, db: AsyncSession, *, scope_ids: Optional[Sequence[UUID]],
    ) -> dict[str, Any]:
        data = await self.load(db)
        world = data.get("world", {})
        usd_rate = _num(world.get("usd_rate")) or 0.0
        pm = self._price_map(data.get("energyPrices", {}), usd_rate)
        mix: dict[str, float] = {f: 0.0 for f in FUELS}

        # ростер компаний (имена/секторы/scope) из канона
        q = text(
            "SELECT c.code, COALESCE(c.name_short, c.name_ru) AS name, c.id AS cid, "
            "       s.name_ru AS sector, s.color_hex AS color "
            "FROM companies c LEFT JOIN sectors s ON s.id = c.sector_id "
            "WHERE c.is_active = true AND c.code <> 'uzassets'"
        )
        rows = (await db.execute(q)).all()
        scope = {str(i) for i in scope_ids} if scope_ids is not None else None

        companies: list[dict[str, Any]] = []
        pf_total = 0.0
        pf_energy = 0.0
        pf_import = 0.0
        prod_count = 0
        for code, name, cid, sector, color in rows:
            if scope is not None and str(cid) not in scope:
                continue
            block = (data.get("companies", {}) or {}).get(code, {})
            prods = [self._calc_product(p, pm) for p in (block.get("products") or [])]
            prod_count += len(prods)
            c_total = sum(p["total_cost"] for p in prods if p["total_cost"] is not None)
            c_energy = sum(p["energy_cost"] * p["output"] for p in prods if p["output"])
            for p in prods:  # энергомикс по видам топлива (для донат-чарта)
                if p["output"] > 0:
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
            pf_total += c_total
            pf_energy += c_energy
            pf_import += imp_cost
            filled = [p for p in prods if p["output"] > 0]
            companies.append({
                "code": code, "name": name, "sector": sector or "—",
                "color": color or "#94A3B8",
                "product_count": len(prods),
                "priced_count": len(filled),
                "total_cost": round(c_total, 1) if c_total else None,
                "energy_cost": round(c_energy, 1) if c_energy else None,
                "energy_share": (round(c_energy / c_total * 100, 1) if c_total > 0 else None),
                "import_cost": round(imp_cost, 1) if imp_cost else None,
                "imports": imports_out,
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
            "energyPrices": data.get("energyPrices", {}),
            "world": world,
            "fuel_labels": FUEL_LABELS,
            "companies": companies,
            "energy_mix": energy_mix,
            "portfolio": {
                "total_cost": round(pf_total, 1) if pf_total else None,
                "energy_cost": round(pf_energy, 1) if pf_energy else None,
                "components_cost": (round(pf_total - pf_energy, 1) if pf_total > 0 else None),
                "energy_share": (round(pf_energy / pf_total * 100, 1) if pf_total > 0 else None),
                "import_cost": round(pf_import, 1) if pf_import else None,
                "company_count": len(companies),
                "product_count": prod_count,
                "priced_count": sum(c["priced_count"] for c in companies),
            },
            "generated_at": datetime.now(UTC).isoformat(),
        }

    # ─── Правки ──────────────────────────────────────────────────────
    async def save_prices(
        self, db: AsyncSession, prices: dict[str, Any], world: dict[str, Any],
        *, user_email: str, user_id: Optional[str],
    ) -> dict[str, Any]:
        data = await self.load(db)
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
        await self._write(db, data)
        await self._audit(db, user_email, user_id, "unit_cost.prices.update", "цены энергоносителей + мировые")
        return {"energyPrices": clean, "world": data.get("world", {})}

    async def save_company(
        self, db: AsyncSession, code: str, products: list[dict[str, Any]],
        imports: list[dict[str, Any]], *, cid_in_scope: bool,
        user_email: str, user_id: Optional[str],
    ) -> dict[str, Any]:
        if not cid_in_scope:
            raise HTTPException(403, "Нет доступа к компании")
        data = await self.load(db)
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
            for f in FUELS:
                v = _num((p.get("energy") or {}).get(f))
                if v is not None:
                    energy[f] = v
            comps = []
            for c in (p.get("components") or []):
                comps.append({"name": str(c.get("name", "")).strip()[:80],
                              "value": _num(c.get("value")) or 0.0})
            clean_products.append({
                "name": str(p.get("name", "")).strip()[:120],
                "unit": str(p.get("unit", "")).strip()[:32],
                "output": _num(p.get("output")) or 0.0,
                "energy": energy, "components": comps,
            })
        data.setdefault("companies", {})[code] = {
            "products": clean_products, "imports": clean_imports,
        }
        await self._write(db, data)
        await self._audit(db, user_email, user_id, "unit_cost.company.update", f"продукты {code}")
        return {"code": code, "products": clean_products, "imports": clean_imports}

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
