"""Unit tests для детерминированного движка прогноза (app.core.forecast).

Без БД. Проверяют честные fallback (нет истории → method='none', не выдумываем),
приоритет методов квартального прогноза, коридор и клампы знака.
"""
import pytest

from app.core.forecast import (
    forecast_annual,
    forecast_quarters,
    seasonal_shares,
    split_by_shares,
)

pytestmark = pytest.mark.unit


# ─────────────────────────── квартальный ───────────────────────────


def test_quarters_pace_below_plan():
    # Факт Q1-Q2 = 90% плана → прогноз Q3-Q4 = план × 0.9.
    r = forecast_quarters([100, 100, 100, 100], [90, 90, None, None])
    assert r.method == "pace"
    q3 = next(p for p in r.projections if p.period == "q3")
    assert q3.value == pytest.approx(90.0)
    # ожидаемый год = 90+90 + 90+90 = 360
    assert r.expected_year == pytest.approx(360.0)
    assert r.confidence == "medium"  # 2 завершённых квартала


def test_quarters_pace_confidence_high_with_three_done():
    r = forecast_quarters([50, 50, 50, 50], [55, 55, 55, None])
    assert r.method == "pace"
    assert r.confidence == "high"
    q4 = next(p for p in r.projections if p.period == "q4")
    assert q4.value == pytest.approx(55.0)


def test_quarters_no_fact_returns_plan():
    r = forecast_quarters([10, 20, 30, 40], [None, None, None, None])
    assert r.method == "plan"
    assert r.expected_year == pytest.approx(100.0)
    assert r.confidence == "low"


def test_quarters_year_complete_is_actual():
    r = forecast_quarters([10, 10, 10, 10], [12, 11, 9, 8])
    assert r.method == "actual"
    assert r.projections == []
    assert r.expected_year == pytest.approx(40.0)


def test_quarters_run_rate_when_no_plan():
    # План отсутствует → pace невозможен → run-rate.
    r = forecast_quarters([None, None, None, None], [30, 30, None, None])
    assert r.method == "run_rate"
    # YTD=60, доля=0.5 → год≈120, остаток 60 на 2 кв = 30/кв
    q3 = next(p for p in r.projections if p.period == "q3")
    assert q3.value == pytest.approx(30.0)
    assert r.expected_year == pytest.approx(120.0)


def test_quarters_seasonal_from_prior_year():
    # Плана нет, но есть прошлый год с сезонностью, факт только Q1.
    r = forecast_quarters(
        [None, None, None, None], [100, None, None, None],
        prior_q_fact=[100, 200, 300, 400],  # прошлый год: Q1 = 10% итога
    )
    assert r.method == "seasonal"
    # год_est = 100 × (1000/100) = 1000; Q2 = 20% = 200
    q2 = next(p for p in r.projections if p.period == "q2")
    assert q2.value == pytest.approx(200.0)


def test_quarters_nonneg_low_clamped_to_zero():
    # Большой разброс темпа не должен давать отрицательный низ коридора у неотриц. ряда.
    r = forecast_quarters([100, 100, 100, 100], [10, 190, None, None])
    q3 = next(p for p in r.projections if p.period == "q3")
    assert q3.low is not None and q3.low >= 0.0


def test_quarters_empty_is_none():
    r = forecast_quarters([None, None, None, None], [None, None, None, None])
    assert r.method == "none"
    assert r.confidence == "none"


# ─────────────────────────── годовой ───────────────────────────


def test_annual_insufficient_history():
    r = forecast_annual([2025], [100], horizon=2)
    assert r.method == "none"
    assert r.projections == []
    assert "≥2" in r.note


def test_annual_ols_linear_trend():
    # Строго линейный ряд +10/год → тренд продолжается.
    r = forecast_annual([2022, 2023, 2024, 2025], [100, 110, 120, 130],
                        horizon=2, method="ols")
    assert r.method == "ols"
    p2026 = next(p for p in r.projections if p.period == "2026")
    p2027 = next(p for p in r.projections if p.period == "2027")
    assert p2026.value == pytest.approx(140.0)
    assert p2027.value == pytest.approx(150.0)
    assert r.confidence == "high"  # идеальная подгонка, 4 точки


def test_annual_cagr_growth():
    # Удвоение каждый год (все >0) → auto выбирает CAGR ~100%.
    r = forecast_annual([2023, 2024, 2025], [100, 200, 400], horizon=1, method="auto")
    assert r.method == "cagr"
    p = r.projections[0]
    assert p.value == pytest.approx(800.0, rel=0.01)


def test_annual_auto_picks_ols_for_mixed_sign():
    r = forecast_annual([2023, 2024, 2025], [-50, 0, 50], horizon=1, method="auto")
    assert r.method == "ols"  # есть неположительные → не CAGR
    assert r.projections[0].value == pytest.approx(100.0)


def test_annual_nonneg_corridor_low_clamped():
    r = forecast_annual([2023, 2024, 2025], [30, 20, 10], horizon=3, method="ols")
    # убывающий тренд уйдёт ниже нуля к 2028 — низ коридора клампится к 0
    for p in r.projections:
        assert p.low is None or p.low >= 0.0


def test_annual_corridor_widens_with_horizon():
    r = forecast_annual([2022, 2023, 2024, 2025], [100, 108, 121, 133],
                        horizon=3, method="ols")
    widths = [
        (p.high - p.low) for p in r.projections
        if p.high is not None and p.low is not None
    ]
    # коридор дальних лет шире ближних
    assert widths == sorted(widths)


def test_seasonal_shares_even():
    s = seasonal_shares([[25, 25, 25, 25], [10, 10, 10, 10]])
    assert s == pytest.approx([0.25, 0.25, 0.25, 0.25])


def test_seasonal_shares_skewed_h2():
    # выпуск смещён во 2-е полугодие
    s = seasonal_shares([[10, 20, 30, 40], [10, 20, 30, 40]])
    assert s == pytest.approx([0.1, 0.2, 0.3, 0.4])


def test_seasonal_shares_none_when_incomplete():
    assert seasonal_shares([[10, 20, None, 40]]) is None
    assert seasonal_shares([]) is None


def test_split_by_shares_distributes_annual():
    q = split_by_shares(1000, [0.1, 0.2, 0.3, 0.4])
    assert q == pytest.approx([100, 200, 300, 400])
    assert sum(q) == pytest.approx(1000)


def test_split_by_shares_guards():
    assert split_by_shares(None, [0.25] * 4) is None
    assert split_by_shares(100, None) is None
    assert split_by_shares(100, [0.5, 0.5]) is None


def test_result_to_dict_shape():
    r = forecast_annual([2024, 2025], [100, 110], horizon=1)
    d = r.to_dict()
    assert set(d.keys()) == {
        "method", "confidence", "points_used", "note", "expected_year", "projections",
    }
    assert d["projections"] and set(d["projections"][0].keys()) == {
        "period", "value", "low", "high",
    }
