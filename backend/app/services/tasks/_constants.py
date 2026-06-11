"""Tasks presentation constants — STATUS_META + direction palette.
Verbatim from legacy (index.html lines 50585+); single source of truth.
"""

# Status presentation. Order matches legacy STATUSES; labels/colors mirror
# SLABELS/SDOTS. Drives Kanban column ordering and chip styling.
STATUS_META = [
    ("new",       "Не начато",         "#CBD5E1"),
    ("init",      "Инициировано",      "#7F77DD"),
    ("active",    "В процессе",        "#378ADD"),
    ("review",    "На согласовании",   "#EF9F27"),
    ("done",      "Завершено",         "#1D9E75"),
    ("quarterly", "Ежеквартально",     "#A855F7"),
    ("monthly",   "Ежемесячно",        "#6366F1"),
    ("ongoing",   "Постоянно",         "#06B6D4"),
]


# Direction code → (label, color). Phase 16.
DIRECTION_PALETTE = {
    "strategy":    ("Стратегическое управление",          "#1e2787"),
    "finance":     ("Финансы / риски / аудит",            "#D97706"),
    "procurement": ("Система закупок",                    "#3B6D11"),
    "orgdev":      ("Организационное развитие",           "#534AB7"),
    "digital":     ("Цифровизация",                       "#1D9E75"),
    "operations":  ("Операционная эффективность",         "#EF4444"),
    "governance":  ("Корпоративное управление",           "#72243E"),
    "esg":         ("ESG",                                "#1D9E75"),
    "pr":          ("Связи с общественностью",            "#D4537E"),
    "pmo":         ("PMO",                                "#2563EB"),
    "analytics":   ("Сводный отдел",                      "#7C3AED"),
}


def enrich_direction_meta(items):
    """For each item with non-null direction string, populate direction_meta dict."""
    for item in items:
        if getattr(item, "direction_meta", None) is not None:
            continue
        code = getattr(item, "direction", None)
        if not code:
            continue
        code = str(code).lower().strip()
        if code in DIRECTION_PALETTE:
            label, color = DIRECTION_PALETTE[code]
            item.direction_meta = {"code": code, "label": label, "color": color}
