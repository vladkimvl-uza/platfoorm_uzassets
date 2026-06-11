"""Pure helpers / constants for ESG domain (no DB / no IO)."""
from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Optional

from app.models.company import Company
from app.models.esg import ESGMetric
from app.schemas.esg import ESGIssueBrief, ESGMetricBrief

PILLARS = ["E", "S", "G"]

SEVERITY_META = [
    {"key": "low",      "label": "Низкая",       "color": "#7DC4A0"},
    {"key": "med",      "label": "Средняя",      "color": "#EF9F27"},
    {"key": "high",     "label": "Высокая",      "color": "#E24B4A"},
    {"key": "critical", "label": "Критическая", "color": "#991B1B"},
]

# Legacy canonical 3 ESG agencies (`ESG_AGENCIES` in showESGView).
ESG_OVERVIEW_AGENCIES = ["Sustainable Fitch", "S&P ESG", "CDP"]

AGENCY_COLORS = {
    "Sustainable Fitch": "#1D9E75",
    "S&P ESG":           "#378ADD",
    "CDP":               "#EF9F27",
    "Sustainalytics":    "#7F77DD",
    "MSCI":              "#A855F7",
}

SECTOR_LABELS_RU = {
    "mining_metallurgy":        "Горно-металлургия",
    "oil_gas":                  "Нефтегаз",
    "energy":                   "Энергетика",
    "transport_communications": "Транспорт и связь",
    "other":                    "Другие",
    "mining":                   "Горнодобыча",
    "oilgas":                   "Нефтегаз",
    "transport":                "Транспорт",
    "telecom":                  "Телеком",
    "finance":                  "Финансы",
    "chemical":                 "Химия",
    "construction":             "Строительство",
}

SECTOR_FALLBACK_COLORS = {
    "mining_metallurgy":        "#9B8EC4",
    "oil_gas":                  "#1D9E75",
    "energy":                   "#EF9F27",
    "transport_communications": "#378ADD",
    "other":                    "#888780",
    "mining":                   "#9B8EC4",
    "oilgas":                   "#1D9E75",
    "transport":                "#378ADD",
    "telecom":                  "#D4537E",
    "finance":                  "#534AB7",
    "chemical":                 "#A855F7",
    "construction":             "#888780",
}


def esg_rating_to_score(rating: Optional[str]) -> Optional[float]:
    """Legacy `_esgRatingToScore` — convert rating text to 0..10 score."""
    if not rating:
        return None
    rv = str(rating).strip().upper()
    try:
        n = int(rv)
        if 0 <= n <= 5 and len(rv) <= 3:
            return float((5 - n) * 2)
        if 0 <= n <= 100:
            return n / 10.0
    except ValueError:
        pass
    letter_map = {
        "AAA": 10, "AA+": 9.5, "AA": 9, "AA-": 8.5,
        "A+": 8.2, "A": 7.7, "A-": 7.2,
        "BBB+": 6.6, "BBB": 6, "BBB-": 5.4,
        "BB+": 4.8, "BB": 4.2, "BB-": 3.6,
        "B+": 3.2, "B": 2.7, "B-": 2.2,
        "CCC+": 1.8, "CCC": 1.4, "CCC-": 1,
        "CC": 0.7, "C": 0.4, "D": 0, "F": 0,
    }
    return letter_map.get(rv)


def esg_score_to_letter(s: Optional[float]) -> str:
    if s is None:
        return "—"
    thresholds = [
        (9.3, "AA"), (8.5, "AA-"), (8.0, "A+"), (7.5, "A"), (7.0, "A-"),
        (6.5, "BBB+"), (5.8, "BBB"), (5.2, "BBB-"),
        (4.6, "BB+"), (4.0, "BB"), (3.4, "BB-"),
        (3.0, "B+"), (2.5, "B"), (2.0, "B-"),
        (1.6, "CCC+"), (1.2, "CCC"), (0.8, "CCC-"),
        (0.4, "CC"),
    ]
    for limit, letter in thresholds:
        if s >= limit:
            return letter
    return "C"


def is_recent_rating(text_date: Optional[str], parsed_date: Optional[date]) -> bool:
    cy = datetime.now(UTC).year
    if parsed_date is not None:
        return parsed_date.year >= (cy - 1)
    if not text_date:
        return False
    s = str(text_date)
    return str(cy) in s or str(cy - 1) in s


def sector_label(code: Optional[str]) -> str:
    if not code:
        return SECTOR_LABELS_RU["other"]
    norm = code.lower().replace("-", "_")
    return SECTOR_LABELS_RU.get(norm, code)


def sector_fallback_color(code: Optional[str]) -> str:
    if not code:
        return "#888780"
    norm = code.lower().replace("-", "_")
    return SECTOR_FALLBACK_COLORS.get(norm, "#888780")


def company_abbr(co: Company) -> str:
    code = (co.code or "").strip()
    if not code:
        return "?"
    return code.upper() if len(code) <= 6 else code[:4].upper()


def attainment_pct(value: Optional[Decimal], target: Optional[Decimal]) -> Optional[float]:
    if value is None or target is None or target == 0:
        return None
    try:
        return round(float(value) / float(target) * 100, 1)
    except (ValueError, ZeroDivisionError):
        return None


def benchmark_diff_pct(value: Optional[Decimal], benchmark: Optional[Decimal]) -> Optional[float]:
    if value is None or benchmark is None or benchmark == 0:
        return None
    try:
        return round((float(value) - float(benchmark)) / float(benchmark) * 100, 1)
    except (ValueError, ZeroDivisionError):
        return None


def metric_to_brief(m: ESGMetric, company_code: Optional[str] = None) -> ESGMetricBrief:
    return ESGMetricBrief(
        id=m.id, company_id=m.company_id, year=m.year, pillar=m.pillar,
        metric_code=m.metric_code, metric_name=m.metric_name,
        value=m.value, unit=m.unit, target=m.target, benchmark=m.benchmark,
        notes=m.notes,
        target_attainment_pct=attainment_pct(m.value, m.target),
        benchmark_diff_pct=benchmark_diff_pct(m.value, m.benchmark),
    )


def company_score_from_metrics(metrics: list[ESGMetric]) -> dict:
    """Compute E/S/G scores (0..100) for a company from its metrics."""
    scores: dict[str, list[float]] = {"E": [], "S": [], "G": []}
    for m in metrics:
        if m.pillar not in scores or m.value is None:
            continue
        if m.target and m.target != 0:
            contrib = min(100.0, max(0.0, float(m.value) / float(m.target) * 100))
            scores[m.pillar].append(contrib)
        elif m.benchmark and m.benchmark != 0:
            diff = abs(float(m.value) - float(m.benchmark)) / float(m.benchmark)
            contrib = max(0.0, 100.0 - diff * 200)
            scores[m.pillar].append(contrib)

    out: dict[str, Optional[float]] = {}
    for p, lst in scores.items():
        out[p] = round(sum(lst) / len(lst), 1) if lst else None
    valid = [v for v in out.values() if v is not None]
    out["overall"] = round(sum(valid) / len(valid), 1) if valid else None
    return out


def issue_to_brief(i, co_code: Optional[str], co_name: Optional[str]) -> ESGIssueBrief:
    return ESGIssueBrief(
        id=i.id, company_id=i.company_id,
        company_code=co_code, company_name=co_name,
        pillar=i.pillar, title=i.title, description=i.description,
        severity=i.severity, status=i.status, created_at=i.created_at,
    )
