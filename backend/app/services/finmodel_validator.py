"""FinModel v2 validator — Phase 1.6.

Returns list[ValidationIssue]. Runs server-side on every save (auth-grade
truth) and can also run client-side (logic mirrored in Pinia store).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, List

from app.schemas.finmodel import ValidationIssue

_ZERO = Decimal("0")
_TOL = Decimal("0.01")


def validate(values: Dict[str, Decimal]) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []

    def g(code: str) -> Decimal:
        v = values.get(code)
        return v if isinstance(v, Decimal) else _ZERO

    # 1. Balance must equal (Active = Passive)
    delta = g("780") - g("400")
    if abs(delta) > _TOL:
        issues.append(ValidationIssue(
            rule_id="balance_mismatch", severity="error", row_code="CHECK",
            message_ru=f"Баланс не сходится: ПАССИВ − АКТИВ = {delta}",
            message_en=f"Balance mismatch: PASSIVE − ASSET = {delta}",
        ))

    # 2. Equity non-negative
    if g("480") < _ZERO:
        issues.append(ValidationIssue(
            rule_id="equity_negative", severity="warning", row_code="480",
            message_ru=f"Отрицательный капитал ({g('480')})",
            message_en=f"Negative equity ({g('480')})",
        ))

    # 3. COGS sign (PL_020 must be ≤ 0)
    if g("PL_020") > _ZERO:
        issues.append(ValidationIssue(
            rule_id="cogs_sign", severity="warning", row_code="PL_020",
            message_ru="Себестоимость должна быть отрицательной (расход)",
            message_en="COGS should be negative (expense)",
        ))

    # 4. Operating expenses (PL_050..PL_080 sequence)
    for code in ("PL_050", "PL_060", "PL_070"):
        if g(code) > _ZERO:
            issues.append(ValidationIssue(
                rule_id=f"{code}_sign", severity="warning", row_code=code,
                message_ru=f"{code}: операционные расходы должны быть ≤ 0",
                message_en=f"{code}: operating expenses should be ≤ 0",
            ))

    # 5. Net income vs revenue sanity
    if g("PL_270") > g("PL_010") and g("PL_010") > _ZERO:
        issues.append(ValidationIssue(
            rule_id="net_exceeds_revenue", severity="info", row_code="PL_270",
            message_ru="Чистая прибыль больше выручки — проверьте",
            message_en="Net income exceeds revenue — please verify",
        ))

    # 6. Receivables vs revenue
    if g("210") > g("PL_010") * Decimal("2") and g("210") > _ZERO:
        issues.append(ValidationIssue(
            rule_id="receivables_high", severity="warning", row_code="210",
            message_ru="Дебиторская задолженность > 2× выручки — высокий риск",
            message_en="Receivables > 2× revenue — high risk",
        ))

    # 7. Current ratio (390/600)
    if g("600") > _ZERO and g("390") / g("600") < Decimal("0.5"):
        issues.append(ValidationIssue(
            rule_id="liquidity_low", severity="info", row_code="390",
            message_ru="Низкая ликвидность: текущие активы < 50% краткосрочных обязательств",
            message_en="Low liquidity: current assets < 50% of current liabilities",
        ))

    # 8. Debt-to-equity
    debt_proxy = g("490") + g("730") + g("740")
    if g("480") > _ZERO and debt_proxy / g("480") > Decimal("3"):
        issues.append(ValidationIssue(
            rule_id="leverage_high", severity="info", row_code="490",
            message_ru="Высокая долговая нагрузка: Долг/Капитал > 3×",
            message_en="High leverage: Debt/Equity > 3×",
        ))

    return issues
