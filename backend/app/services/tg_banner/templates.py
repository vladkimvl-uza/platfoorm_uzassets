"""Banner palette + label templates (Phase B).

Severity gradient overrides everything else (it sets the dominant background
gradient), while module supplies the accent pill colour and the right-side
text label.
"""
from typing import TypedDict


class Palette(TypedDict):
    bg_from: str     # gradient start (left, hex)
    bg_to: str       # gradient end   (right, hex)
    accent: str      # module accent (small pill / left strip)
    fg: str          # foreground text on gradient
    sub_fg: str      # secondary text


# ── Severity palettes — drive the gradient background ──────────────────

SEVERITY_PALETTES: dict[str, Palette] = {
    "info": Palette(
        bg_from="#1E2A4A",
        bg_to="#534AB7",
        accent="#7F77DD",
        fg="#FFFFFF",
        sub_fg="rgba(255,255,255,0.78)",
    ),
    "success": Palette(
        bg_from="#0F6E56",
        bg_to="#1D9E75",
        accent="#34D399",
        fg="#FFFFFF",
        sub_fg="rgba(255,255,255,0.82)",
    ),
    "warning": Palette(
        bg_from="#854F0B",
        bg_to="#EF9F27",
        accent="#FBBF24",
        fg="#FFFFFF",
        sub_fg="rgba(255,255,255,0.82)",
    ),
    "critical": Palette(
        bg_from="#791F1F",
        bg_to="#E24B4A",
        accent="#FCA5A5",
        fg="#FFFFFF",
        sub_fg="rgba(255,255,255,0.82)",
    ),
}

# Aliases — some notifications use "normal"/"high"/"low" instead of severity
SEVERITY_ALIASES: dict[str, str] = {
    "normal": "info",
    "low":    "info",
    "high":   "warning",
    "high_priority": "warning",
}


# ── Module → label + optional severity bias ────────────────────────────

class ModuleSpec(TypedDict, total=False):
    label_ru: str          # right-side text on banner
    icon_label: str        # small one-word label inside accent pill (left)
    default_severity: str  # if caller didn't pass severity


MODULES: dict[str, ModuleSpec] = {
    "kpi":         ModuleSpec(label_ru="KPI",            icon_label="KPI",   default_severity="warning"),
    "bp":          ModuleSpec(label_ru="Бизнес-план",    icon_label="BP",    default_severity="info"),
    "credit":      ModuleSpec(label_ru="Кредит",         icon_label="CR",    default_severity="critical"),
    "loan":        ModuleSpec(label_ru="Кредит",         icon_label="CR",    default_severity="critical"),
    "procurement": ModuleSpec(label_ru="Закупки",        icon_label="PR",    default_severity="info"),
    "tasks":       ModuleSpec(label_ru="Задачи",         icon_label="TS",    default_severity="info"),
    "projects":    ModuleSpec(label_ru="Проекты",        icon_label="PJ",    default_severity="info"),
    "deadline":    ModuleSpec(label_ru="Дедлайн",        icon_label="DL",    default_severity="warning"),
    "moderation":  ModuleSpec(label_ru="Модерация",      icon_label="MOD",   default_severity="info"),
    "mfa":         ModuleSpec(label_ru="Безопасность",   icon_label="2FA",   default_severity="info"),
    "auth":        ModuleSpec(label_ru="Доступ",         icon_label="ACL",   default_severity="info"),
    "rbac":        ModuleSpec(label_ru="Доступ",         icon_label="ACL",   default_severity="info"),
    "audit":       ModuleSpec(label_ru="Аудит",          icon_label="AUD",   default_severity="info"),
    "esg":         ModuleSpec(label_ru="ESG",            icon_label="ESG",   default_severity="info"),
    "governance":  ModuleSpec(label_ru="Корп. упр.",     icon_label="GOV",   default_severity="info"),
    "system":      ModuleSpec(label_ru="Система",        icon_label="SYS",   default_severity="info"),
}

ALLOWED_MODULES = frozenset(MODULES.keys())
ALLOWED_SEVERITIES = frozenset(SEVERITY_PALETTES.keys())


def resolve_severity(severity: str) -> str:
    """Map an aliased priority into a known severity key (default: info)."""
    s = (severity or "info").lower().strip()
    if s in SEVERITY_PALETTES:
        return s
    return SEVERITY_ALIASES.get(s, "info")


def resolve_module(module: str) -> str:
    """Map a module string into a known module key (default: system)."""
    m = (module or "system").lower().strip()
    if m in MODULES:
        return m
    return "system"


def palette_for(severity: str) -> Palette:
    return SEVERITY_PALETTES[resolve_severity(severity)]


def module_spec_for(module: str) -> ModuleSpec:
    return MODULES[resolve_module(module)]
