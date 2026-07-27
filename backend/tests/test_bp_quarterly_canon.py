"""Юнит-тесты канона «кварталы БП = нарастающий итог» (без БД).

Пинуют семантику после фикса двойного счёта:
- ytd_to_deltas: «за квартал» = ytd(qn) − ytd(qn−1), честный None при разрывах;
- seasonal_shares: вход — дельты (не YTD), знакопеременные ряды отбрасываются;
- kpi_bp_effective: фолбэк на q*-поля индикатора только ПАРОЙ целиком
  (не смешивать BP-YTD с поквартальными полями KPI).
"""
from decimal import Decimal

import pytest

from app.core.forecast import seasonal_shares
from app.models.bp_kpi import KpiIndicator
from app.services.bp_kpi_helpers import kpi_bp_effective, ytd_to_deltas


def D(x) -> Decimal:
    return Decimal(str(x))


class TestYtdToDeltas:
    def test_full_year_flat(self):
        assert ytd_to_deltas([D(25), D(50), D(75), D(100)]) == [D(25), D(25), D(25), D(25)]

    def test_q1_delta_equals_ytd(self):
        assert ytd_to_deltas([D("134.9"), None, None, None]) == [D("134.9"), None, None, None]

    def test_missing_q1_blocks_q2(self):
        # ung-кейс: у компании нет q1, есть полугодие — оно НЕ должно лечь в «Q2»
        assert ytd_to_deltas([None, D(6452), None, None]) == [None, None, None, None]

    def test_gap_blocks_only_next(self):
        assert ytd_to_deltas([D(10), None, D(30), D(45)]) == [D(10), None, None, D(15)]

    def test_negative_delta_preserved(self):
        # прибыль: убыточный квартал → YTD падает, дельта отрицательная (честно)
        assert ytd_to_deltas([D(10), D(5), D(20), D(15)]) == [D(10), D(-5), D(15), D(-5)]

    def test_sum_of_deltas_equals_q4_ytd(self):
        ytd = [D(25), D(50), D(75), D(100)]
        assert sum(ytd_to_deltas(ytd)) == ytd[-1]


class TestSeasonalSharesOnDeltas:
    def test_flat_ytd_gives_flat_shares(self):
        deltas = [float(x) for x in ytd_to_deltas([D(25), D(50), D(75), D(100)])]
        assert seasonal_shares([deltas]) == pytest.approx([0.25, 0.25, 0.25, 0.25])

    def test_raw_ytd_feed_would_skew_to_q4(self):
        # Регрессия-иллюстрация: сырой YTD даёт монотонные 10/20/30/40% — потому
        # конвертация в дельты перед seasonal_shares ОБЯЗАТЕЛЬНА (forecast_service).
        assert seasonal_shares([[25, 50, 75, 100]]) == pytest.approx([0.1, 0.2, 0.3, 0.4])

    def test_mixed_sign_row_rejected(self):
        deltas = [float(x) for x in ytd_to_deltas([D(10), D(5), D(20), D(15)])]
        assert seasonal_shares([deltas]) is None

    def test_incomplete_row_rejected(self):
        deltas = [25.0, None, None, None]
        assert seasonal_shares([deltas]) is None


class TestKpiBpEffectivePairwise:
    @staticmethod
    def _ind(**kw) -> KpiIndicator:
        return KpiIndicator(bp_metric_key="revenue", **kw)

    def test_bp_pair_used_when_full(self):
        ind = self._ind(q2_plan=D(1), q2_fact=D(2))
        assert kpi_bp_effective(ind, "q2", {"plan": D(100), "fact": D(90)}) == (D(100), D(90), "up")

    def test_partial_bp_never_mixed_with_indicator(self):
        # BP-план (YTD) есть, BP-факта нет → факт индикатора НЕ подставляется
        ind = self._ind(q2_plan=D(50), q2_fact=D(45))
        plan, fact, _ = kpi_bp_effective(ind, "q2", {"plan": D(100), "fact": None})
        assert plan == D(100) and fact is None

    def test_full_fallback_when_bp_cell_empty(self):
        ind = self._ind(q2_plan=D(50), q2_fact=D(45))
        plan, fact, _ = kpi_bp_effective(ind, "q2", {"plan": None, "fact": None})
        assert plan == D(50) and fact == D(45)

    def test_annual_no_indicator_fallback(self):
        ind = self._ind(q2_plan=D(50), q2_fact=D(45))
        plan, fact, _ = kpi_bp_effective(ind, "annual", {"plan": None, "fact": None})
        assert plan is None and fact is None
