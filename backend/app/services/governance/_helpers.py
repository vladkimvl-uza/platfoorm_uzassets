"""Pure helpers for Governance domain (no DB / no IO)."""
from __future__ import annotations

from typing import Optional

from app.models.company import Company
from app.models.governance import BoardMember, GovernanceData
from app.schemas.governance import (
    BoardMemberBrief,
    DiversityStat,
    GovernanceCompanyScore,
    GovernanceDataBrief,
)

# Role palette used for diversity_split block on overview dashboard
ROLE_PALETTE = [
    ("independent",   "Независимые",        "#1D9E75"),
    ("chairman",      "Председатели",       "#7F77DD"),
    ("state_rep",     "Гос. представители", "#A855F7"),
    ("other",         "Прочие",             "#94A3B8"),
]


def committees_present(d: GovernanceData) -> tuple[int, int]:
    """(present, total=5) по КАНОНИЧЕСКОМУ набору комитетов, единому со счётчиком
    «X из 5» в UI: Аудит · Стратегия · Назначения-и-вознаграждения (nomination ИЛИ
    remuneration — ОДИН комитет) · Антикор. · Введение.

    Расширенные (anticorr/induction) хранятся в GovernanceData.payload, а не колонками.
    Единый источник — чтобы score, committees_count и чип UI не расходились (раньше
    score считал nomination+remuneration как 2 из 4 и игнорировал anticorr/введение)."""
    pl = d.payload or {}
    flags = [
        bool(d.has_audit_committee),
        bool(d.has_strategy_committee),
        bool(d.has_nomination_committee or d.has_remuneration_committee),
        bool(pl.get("anticorr")),
        bool(pl.get("induction")),
    ]
    return (sum(1 for f in flags if f), len(flags))


def governance_score(d: GovernanceData) -> Optional[float]:
    """Composite governance score 0..100 from a GovernanceData row.

    Weights:
      25% independence ratio (target >=33%)
      15% women ratio (target >=20%)
      10% foreign ratio (target >=10%)
      25% committees present (по каноническому набору из 5, см. committees_present)
      15% attendance (target >=80%)
      10% meetings (target >=4/year)
    """
    if d.board_size is None or d.board_size == 0:
        return None

    parts: list[tuple[float, float]] = []

    if d.independent_directors_count is not None:
        ratio = d.independent_directors_count / d.board_size
        parts.append((0.25, min(1.0, ratio / 0.33)))
    if d.women_directors_count is not None:
        ratio = d.women_directors_count / d.board_size
        parts.append((0.15, min(1.0, ratio / 0.20)))
    if d.foreign_directors_count is not None:
        ratio = d.foreign_directors_count / d.board_size
        parts.append((0.10, min(1.0, ratio / 0.10)))

    n_committees, total_committees = committees_present(d)
    parts.append((0.25, (n_committees / total_committees) if total_committees else 0.0))

    if d.avg_attendance_pct is not None:
        parts.append((0.15, min(1.0, d.avg_attendance_pct / 80)))
    if d.meetings_per_year is not None:
        parts.append((0.10, min(1.0, d.meetings_per_year / 4)))

    if not parts:
        return None
    total_weight = sum(w for w, _ in parts)
    weighted = sum(w * s for w, s in parts) / total_weight
    return round(weighted * 100, 1)


def governance_score_breakdown(d: GovernanceData) -> list[dict]:
    """Разбор балла по факторам — чтобы пользователь видел, ИЗ ЧЕГО он сложился.

    Считается ровно теми же формулами, что governance_score (один код, одна
    правда): доля от цели, ограниченная 1.0, умноженная на вес.

    ВАЖНО про честность: если фактор не заполнен, он не участвует, а веса
    оставшихся нормируются. Балл при этом выглядит «полным», хотя описывает
    меньше факторов — поэтому `missing=true` возвращается явно, и интерфейс
    обязан показать покрытие.
    """
    if d.board_size is None or d.board_size == 0:
        return []

    n_committees, total_committees = committees_present(d)
    rows: list[dict] = [
        {
            "key": "independence", "label": "Независимые директора",
            "weight": 0.25, "target_text": "≥33% состава",
            "value": (d.independent_directors_count / d.board_size * 100)
                     if d.independent_directors_count is not None else None,
            "value_text": (f"{d.independent_directors_count} из {d.board_size}"
                           if d.independent_directors_count is not None else None),
            "ratio": min(1.0, (d.independent_directors_count / d.board_size) / 0.33)
                     if d.independent_directors_count is not None else None,
        },
        {
            "key": "women", "label": "Женщины в совете",
            "weight": 0.15, "target_text": "≥20% состава",
            "value": (d.women_directors_count / d.board_size * 100)
                     if d.women_directors_count is not None else None,
            "value_text": (f"{d.women_directors_count} из {d.board_size}"
                           if d.women_directors_count is not None else None),
            "ratio": min(1.0, (d.women_directors_count / d.board_size) / 0.20)
                     if d.women_directors_count is not None else None,
        },
        {
            "key": "foreign", "label": "Иностранные директора",
            "weight": 0.10, "target_text": "≥10% состава",
            "value": (d.foreign_directors_count / d.board_size * 100)
                     if d.foreign_directors_count is not None else None,
            "value_text": (f"{d.foreign_directors_count} из {d.board_size}"
                           if d.foreign_directors_count is not None else None),
            "ratio": min(1.0, (d.foreign_directors_count / d.board_size) / 0.10)
                     if d.foreign_directors_count is not None else None,
        },
        {
            "key": "committees", "label": "Комитеты совета",
            "weight": 0.25, "target_text": f"все {total_committees}",
            "value": (n_committees / total_committees * 100) if total_committees else None,
            "value_text": f"{n_committees} из {total_committees}",
            "ratio": (n_committees / total_committees) if total_committees else 0.0,
        },
        {
            "key": "attendance", "label": "Посещаемость заседаний",
            "weight": 0.15, "target_text": "≥80%",
            "value": d.avg_attendance_pct,
            "value_text": (f"{d.avg_attendance_pct:g}%"
                           if d.avg_attendance_pct is not None else None),
            "ratio": min(1.0, d.avg_attendance_pct / 80)
                     if d.avg_attendance_pct is not None else None,
        },
        {
            "key": "meetings", "label": "Заседаний в год",
            "weight": 0.10, "target_text": "≥4",
            "value": d.meetings_per_year,
            "value_text": (f"{d.meetings_per_year:g}"
                           if d.meetings_per_year is not None else None),
            "ratio": min(1.0, d.meetings_per_year / 4)
                     if d.meetings_per_year is not None else None,
        },
    ]

    present = [r for r in rows if r["ratio"] is not None]
    total_weight = sum(r["weight"] for r in present) or 1.0
    for r in rows:
        r["missing"] = r["ratio"] is None
        # Вклад в итоговый балл с учётом нормировки весов по заполненным факторам.
        r["points"] = (round(r["weight"] / total_weight * r["ratio"] * 100, 1)
                       if r["ratio"] is not None else None)
        r["max_points"] = round(r["weight"] / total_weight * 100, 1) if not r["missing"] else None
    return rows


def co_data_to_score_row(d: GovernanceData, co: Company,
                         board_actual: Optional[int] = None) -> GovernanceCompanyScore:
    bs = d.board_size or 0
    indep_pct = round(100 * d.independent_directors_count / bs, 1) if d.independent_directors_count is not None and bs else None
    wm_pct    = round(100 * d.women_directors_count / bs, 1) if d.women_directors_count is not None and bs else None
    fo_pct    = round(100 * d.foreign_directors_count / bs, 1) if d.foreign_directors_count is not None and bs else None

    n_committees, total_committees = committees_present(d)

    payload = d.payload or {}
    sector = co.sector
    sector_color = (
        co.primary_color
        or (sector.color_hex if sector else None)
        or "#888780"
    )
    abbr = (co.code or "").upper() if co.code else None

    def _bool_or_none(v):
        if v is None:
            return None
        return bool(v)

    return GovernanceCompanyScore(
        company_id=co.id,
        company_code=co.code,
        company_name=co.name_short or co.name_ru,   # короткое имя (как в финансах)
        company_abbr=abbr,
        sector_code=(sector.code if sector else None),
        sector_color=sector_color,
        year=d.year,
        board_size=d.board_size,
        independent_count=d.independent_directors_count,
        women_count=d.women_directors_count,
        foreign_count=d.foreign_directors_count,
        board_actual=board_actual,
        # Вакансии = утверждённый размер − факт. Ручное payload.vacant —
        # только фолбэк для записей без board_size: на проде оно расходилось
        # с данными (стояла «1 вакансия» там, где все места заняты).
        vacant_seats=(
            max(0, d.board_size - board_actual)
            if (d.board_size is not None and board_actual is not None)
            else payload.get("vacant")
        ),
        exec_count=payload.get("exec"),
        nonexec_count=payload.get("nonexec"),
        independent_pct=indep_pct,
        women_pct=wm_pct,
        foreign_pct=fo_pct,
        committees_count=n_committees,
        has_all_4_committees=(n_committees == total_committees),
        has_audit_committee=d.has_audit_committee,
        has_remuneration_committee=d.has_remuneration_committee,
        has_nomination_committee=d.has_nomination_committee,
        has_strategy_committee=d.has_strategy_committee,
        has_anticorr_committee=_bool_or_none(payload.get("anticorr")),
        has_procurement_committee=_bool_or_none(payload.get("procurement")),
        has_esg_committee=_bool_or_none(payload.get("esg")),
        has_dno_insurance=_bool_or_none(payload.get("dno")),
        has_induction_program=_bool_or_none(payload.get("induction")),
        meetings_per_year=d.meetings_per_year,
        attendance_pct=d.avg_attendance_pct,
        governance_score=governance_score(d),
        governance_score_1200=payload.get("score"),
        age_avg=payload.get("ageAvg") if payload.get("ageAvg") is not None else d.avg_age,
        age_min=payload.get("ageMin"),
        age_max=payload.get("ageMax"),
    )


def diversity_from_members(members: list[BoardMember]) -> list[DiversityStat]:
    by_role: dict[str, int] = {}
    for m in members:
        rt = m.role_type or "other"
        by_role[rt] = by_role.get(rt, 0) + 1
    total = sum(by_role.values()) or 1
    out = []
    for key, label, color in ROLE_PALETTE:
        cnt = by_role.get(key, 0)
        out.append(DiversityStat(
            label=label, color=color,
            pct=round(100 * cnt / total, 1),
            count=cnt,
        ))
    return out


def data_to_brief(d: GovernanceData) -> GovernanceDataBrief:
    brief = GovernanceDataBrief.model_validate(d, from_attributes=True)
    # Расширенные комитеты (Антикор/Закупки/ESG/D&O/Введение) хранятся в payload
    # JSON, а не колонками модели — model_validate их пропускает. Достаём вручную,
    # как в матрице governance (score_from_data), иначе detail отдаёт их как None
    # и в /workspace?tab=governance виден только урезанный набор комитетов.
    payload = d.payload or {}

    def _b(v):
        return None if v is None else bool(v)

    brief.has_anticorr_committee = _b(payload.get("anticorr"))
    brief.has_procurement_committee = _b(payload.get("procurement"))
    brief.has_esg_committee = _b(payload.get("esg"))
    brief.has_dno_insurance = _b(payload.get("dno"))
    brief.has_induction_program = _b(payload.get("induction"))
    return brief


def member_to_brief(m: BoardMember) -> BoardMemberBrief:
    return BoardMemberBrief.model_validate(m, from_attributes=True)
