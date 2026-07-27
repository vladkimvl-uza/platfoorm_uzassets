"""Детерминированный движок прогноза (без БД, без ИИ).

Честный расчёт в стиле [core/progress.py] и аудит-канона платформы
(«флаг≠факт», «не выдумывать при нехватке данных»): движок даёт числа с
коридором надёжности, а при недостатке истории честно возвращает
`method='none'`/`confidence='none'` с пояснением, а НЕ фабрикует значение.

Два сценария:
- `forecast_quarters(...)` — прогноз оставшихся кварталов текущего года
  (pace-adjusted план → сезонность прошлого года → run-rate) + ожидаемый итог.
- `forecast_annual(...)` — прогноз на будущие годы по годовому ряду
  (auto → CAGR для знакопостоянных растущих рядов, иначе OLS-тренд).

Модуль чистый и юнит-тестируемый: работает с уже извлечёнными числовыми рядами,
ничего не знает ни о моделях БД, ни о KPI-схеме. Извлечение/сопоставление рядов
(в т.ч. matching индикаторов по имени между годами) — забота сервисного слоя.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

Number = Optional[float]

# ─────────────────────────── DTO результата ───────────────────────────


@dataclass
class Projection:
    """Одна прогнозная точка: период + значение + коридор [low; high]."""
    period: str                 # 'q3' | 'q4' | '2027' | ...
    value: Optional[float]
    low: Optional[float] = None
    high: Optional[float] = None


@dataclass
class ForecastResult:
    method: str                 # 'pace'|'seasonal'|'run_rate'|'plan'|'actual'|'ols'|'cagr'|'none'
    projections: list[Projection] = field(default_factory=list)
    confidence: str = "none"    # 'high'|'medium'|'low'|'none'
    points_used: int = 0
    note: str = ""              # человекочитаемое пояснение / причина 'none'
    expected_year: Optional[float] = None  # квартальный: ожидаемый итог года

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "confidence": self.confidence,
            "points_used": self.points_used,
            "note": self.note,
            "expected_year": self.expected_year,
            "projections": [
                {"period": p.period, "value": p.value, "low": p.low, "high": p.high}
                for p in self.projections
            ],
        }


# ─────────────────────────── числовые хелперы ─────────────────────────


def _fin(x: object) -> Optional[float]:
    """None/нечисло/Inf/NaN → None; иначе float."""
    if x is None:
        return None
    try:
        v = float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _stdev(xs: list[float]) -> float:
    """Выборочное СКО (n-1). <2 точек → 0."""
    n = len(xs)
    if n < 2:
        return 0.0
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    return math.sqrt(max(0.0, var))


def _ols(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """Простая линейная регрессия y = a + b·x → (slope b, intercept a)."""
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return 0.0, my
    sxy = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    b = sxy / sxx
    a = my - b * mx
    return b, a


def _r2(ys: list[float], resid: list[float]) -> float:
    """Коэффициент детерминации по остаткам регрессии."""
    n = len(ys)
    if n < 2:
        return 0.0
    my = sum(ys) / n
    ss_tot = sum((y - my) ** 2 for y in ys)
    if ss_tot == 0:
        return 1.0
    ss_res = sum(r * r for r in resid)
    return max(0.0, 1.0 - ss_res / ss_tot)


def _fit_confidence(n: int, r2: float) -> str:
    """Надёжность тренда: число точек × качество подгонки."""
    if n >= 4 and r2 >= 0.8:
        return "high"
    if n >= 3 and r2 >= 0.5:
        return "medium"
    return "low"


# ─────────────────────── сезонность (для будущих лет) ─────────────────


def seasonal_shares(history_quarters: list[list[Number]]) -> Optional[list[float]]:
    """Средние доли кварталов по историческим годам (каждый ряд = [q1..q4]).

    ВХОД — суммы «ЗА квартал» (per-quarter amounts), НЕ нарастающий итог!
    Держатели YTD-рядов (кварталы bp_records) обязаны сначала конвертировать
    через bp_kpi_helpers.ytd_to_deltas — иначе доли монотонно растут к Q4
    независимо от реальной сезонности.

    Возвращает [s1..s4] с суммой 1 (нормализовано), либо None если нет ни одного
    полного знакопостоянного года. Ряд со знакопеременными кварталами (напр.
    прибыль с убыточным кварталом) пропускается — отрицательная «доля» в
    разложении года бессмысленна. Используется, чтобы разложить прогноз ГОДА на
    кварталы будущего года по типичной сезонности показателя.
    """
    acc = [0.0, 0.0, 0.0, 0.0]
    n = 0
    for row in history_quarters:
        vals = [_fin(x) for x in (row or [])][:4]
        if len(vals) < 4 or any(v is None for v in vals):
            continue
        # Знакопостоянство (обещано docstring, теперь и кодом): смешанные знаки
        # дали бы отрицательную долю → искажённые/отрицательные кварталы прогноза.
        if any(v is not None and v < 0 for v in vals):
            continue
        tot = sum(v for v in vals if v is not None)
        if tot <= 0:
            continue
        for i in range(4):
            acc[i] += (vals[i] or 0.0) / tot
        n += 1
    if n == 0:
        return None
    shares = [a / n for a in acc]
    s = sum(shares)
    return [x / s for x in shares] if s > 0 else None


def split_by_shares(
    annual: Number, shares: Optional[list[float]],
) -> Optional[list[Optional[float]]]:
    """Разложить годовое значение по кварталам согласно долям [s1..s4]."""
    a = _fin(annual)
    if a is None or not shares or len(shares) != 4:
        return None
    return [a * s for s in shares]


# ─────────────────────────── квартальный прогноз ──────────────────────


def forecast_quarters(
    q_plan: list[Number],
    q_fact: list[Number],
    *,
    prior_q_fact: Optional[list[Number]] = None,
) -> ForecastResult:
    """Прогноз оставшихся кварталов текущего года + ожидаемый итог года.

    q_plan/q_fact — списки [q1, q2, q3, q4] сумм «ЗА квартал» (per-quarter
    amounts), НЕ нарастающим итогом: вся арифметика (Σфакт, темп, run-rate)
    предполагает независимые кварталы. YTD-ряды (кварталы bp_records) сначала
    конвертировать через bp_kpi_helpers.ytd_to_deltas.
    Короче 4 — дополняются None. Квартал считается «завершённым», если у него
    есть факт (не None).
    prior_q_fact — квартальный факт прошлого года (для сезонного fallback).

    Приоритет методов:
      1. `pace`     — прогноз оставшихся кв. = план_кв × темп (Σфакт/Σплан завершённых);
      2. `seasonal` — доля кв. прошлого года × ожидаемый годовой run-rate;
      3. `run_rate` — экстраполяция среднего факта на остаток года;
      4. `plan`     — факта нет вовсе → прогноз равен плану;
      5. `actual`   — год завершён по всем кварталам → прогнозировать нечего.

    Коридор для `pace` строится из поквартального разброса темпа. Знак:
    если весь наблюдаемый факт ≥0 — нижняя граница коридора клампится к 0.
    """
    plan = [_fin(x) for x in (q_plan or [])][:4]
    fact = [_fin(x) for x in (q_fact or [])][:4]
    plan += [None] * (4 - len(plan))
    fact += [None] * (4 - len(fact))

    done = [i for i in range(4) if fact[i] is not None]
    todo = [i for i in range(4) if fact[i] is None]
    nonneg = all((fact[i] or 0) >= 0 for i in done)

    def _clamp_low(v: Optional[float]) -> Optional[float]:
        if v is None:
            return None
        return max(0.0, v) if nonneg else v

    # 5. Год завершён — прогнозировать нечего.
    if not todo:
        exp = sum(fact[i] for i in done) if done else None
        return ForecastResult("actual", [], "high", 4,
                              "Год завершён по всем кварталам", exp)

    # 4. Факта нет вовсе — прогноз равен плану.
    if not done:
        proj = [Projection(f"q{i + 1}", plan[i]) for i in todo if plan[i] is not None]
        exp = sum(p for p in plan if p is not None) if any(plan[i] is not None for i in range(4)) else None
        note = "Факта пока нет — прогноз равен плану" if proj else "Нет ни факта, ни плана"
        return ForecastResult("plan" if proj else "none", proj,
                              "low" if proj else "none", 0, note, exp)

    ytd = sum(fact[i] for i in done)

    # 1. pace-adjusted план (основной метод).
    pf = [(fact[i], plan[i]) for i in done if plan[i] not in (None, 0)]
    if pf and all(plan[i] is not None for i in todo):
        sum_f = sum(f for f, _ in pf)
        sum_p = sum(p for _, p in pf)
        pace = sum_f / sum_p if sum_p else None
        if pace is not None:
            paces = [f / p for f, p in pf]
            spread = _stdev(paces)
            proj = []
            for i in todo:
                base = plan[i] * pace
                lo = _clamp_low(plan[i] * (pace - spread))
                hi = plan[i] * (pace + spread)
                proj.append(Projection(f"q{i + 1}", base, lo, hi))
            conf = "high" if len(done) >= 3 else ("medium" if len(done) == 2 else "low")
            exp = ytd + sum(p.value for p in proj if p.value is not None)
            return ForecastResult(
                "pace", proj, conf, len(done),
                f"Прогноз = план × темп {pace * 100:.0f}% (по {len(done)} факт. кв.)", exp,
            )

    # 2. Сезонность прошлого года.
    if prior_q_fact:
        pq = [_fin(x) for x in prior_q_fact][:4]
        pq += [None] * (4 - len(pq))
        prior_total = sum(x for x in pq if x is not None)
        prior_done = sum(pq[i] for i in done if pq[i] is not None)
        if prior_total and prior_done:
            # ожидаемый год = факт YTD × (весь прошлый год / прошлый YTD)
            year_est = ytd * (prior_total / prior_done)
            proj = []
            for i in todo:
                share = (pq[i] / prior_total) if pq[i] is not None else None
                val = _clamp_low(year_est * share) if share is not None else None
                proj.append(Projection(f"q{i + 1}", val))
            exp = ytd + sum(p.value for p in proj if p.value is not None)
            return ForecastResult("seasonal", proj, "medium", len(done),
                                  "Сезонность прошлого года × темп текущего", exp)

    # 3. Run-rate.
    share = len(done) / 4
    year_est = ytd / share if share else None
    if year_est is not None:
        rem = year_est - ytd
        per_q = rem / len(todo) if todo else 0.0
        proj = [Projection(f"q{i + 1}", _clamp_low(per_q)) for i in todo]
        exp = ytd + sum(p.value for p in proj if p.value is not None)
        return ForecastResult("run_rate", proj, "low", len(done),
                              "Run-rate: средний факт экстраполирован на остаток года", exp)

    return ForecastResult("none", [], "none", len(done),
                          "Недостаточно данных для квартального прогноза")


# ─────────────────────────── годовой прогноз ──────────────────────────


def forecast_annual(
    years: list[int],
    values: list[Number],
    horizon: int = 2,
    *,
    method: str = "auto",
) -> ForecastResult:
    """Прогноз на `horizon` будущих лет по годовому ряду.

    years/values — параллельные списки (год → значение факта). Точки с None
    игнорируются. Нужно ≥2 валидных точки, иначе `method='none'`.

    method: 'auto' | 'ols' | 'cagr'. 'auto' → CAGR для знакопостоянных (все >0)
    рядов с ≥3 точками, иначе OLS-тренд. Коридор расширяется вдаль от последней
    фактической точки (неопределённость растёт с горизонтом). Нижняя граница
    клампится к 0, если весь ряд неотрицателен.
    """
    pairs = [(int(y), _fin(v)) for y, v in zip(years, values, strict=False)]
    pairs = [(y, v) for y, v in pairs if v is not None]
    pairs.sort(key=lambda t: t[0])
    n = len(pairs)
    if n < 2:
        return ForecastResult("none", [], "none", n,
                              "Недостаточно истории для тренда (нужно ≥2 года)")

    ys = [p[0] for p in pairs]
    vs = [float(p[1]) for p in pairs]  # p[1] уже не None
    last_y = ys[-1]
    horizon = max(1, min(int(horizon), 5))
    future_years = [last_y + k for k in range(1, horizon + 1)]
    nonneg = all(v >= 0 for v in vs)

    def _clamp_low(v: float) -> float:
        return max(0.0, v) if nonneg else v

    chosen = method
    if method == "auto":
        chosen = "cagr" if (n >= 3 and all(v > 0 for v in vs)) else "ols"

    # CAGR — компаундный рост знакопостоянного ряда.
    if chosen == "cagr" and all(v > 0 for v in vs) and ys[-1] != ys[0]:
        cagr = (vs[-1] / vs[0]) ** (1.0 / (ys[-1] - ys[0])) - 1.0
        proj: list[Projection] = []
        for k, fy in enumerate(future_years, start=1):
            base = vs[-1] * (1.0 + cagr) ** k
            band = abs(base) * min(0.5, abs(cagr) * k * 0.5)
            proj.append(Projection(str(fy), base, _clamp_low(base - band), base + band))
        conf = "medium" if n >= 3 else "low"
        return ForecastResult("cagr", proj, conf, n, f"CAGR {cagr * 100:+.1f}%/год")

    # OLS — линейный тренд y = a + b·(year − y0).
    x0 = ys[0]
    xs = [float(y - x0) for y in ys]
    b, a = _ols(xs, vs)
    resid = [vs[i] - (a + b * xs[i]) for i in range(n)]
    se = _stdev(resid) if n >= 3 else abs(b)  # грубая оценка коридора на 2 точках
    r2 = _r2(vs, resid)
    proj = []
    for fy in future_years:
        base = a + b * (fy - x0)
        widen = se * (1.0 + 0.5 * (fy - last_y))
        proj.append(Projection(str(fy), base, _clamp_low(base - widen), base + widen))
    conf = _fit_confidence(n, r2)
    return ForecastResult("ols", proj, conf, n,
                          f"Линейный тренд {b:+.2f}/год (R²={r2:.2f})")
