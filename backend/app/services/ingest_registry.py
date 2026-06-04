"""Реестр целей ИИ-импорта (ingest targets).

Каждый дашборд платформы декларирует здесь свою СХЕМУ данных: какие поля,
каких типов, с какими допустимыми значениями, и подключён ли он к
авто-созданию. ИИ-агент использует этот реестр, чтобы:

  1. КЛАССИФИЦИРОВАТЬ документ — к какому дашборду относятся данные;
  2. ЗНАТЬ структуру выбранного дашборда — какие поля заполнять;
  3. ПОДСТАВИТЬ данные в правильные поля.

Добавить новый дашборд к импорту = добавить сюда IngestTarget (+ при
`supported=True` — серверный путь массового создания).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class IngestField:
    name: str                 # ключ поля (как в схеме создания)
    type: str                 # "str" | "int" | "number" | "date" | "enum" | "email"
    desc: str                 # что это и откуда брать в документе
    enum: list[str] = field(default_factory=list)   # допустимые значения для type=enum
    required: bool = False


@dataclass
class IngestTarget:
    key: str                  # машинный код цели
    label: str                # человекочитаемое имя дашборда
    when: str                 # когда документ относится сюда (для классификатора)
    fields: list[IngestField]
    supported: bool = False    # подключён ли к авто-созданию прямо сейчас
    nests_tasks: bool = False  # есть ли иерархия (проект → задачи)


# ─── статусы/приоритеты задач (зеркало фронта Конструктора) ─────────
TASK_STATUS = ["new", "init", "active", "quarterly", "monthly", "ongoing"]
PRIORITY = ["high", "medium", "low"]

_TASK_FIELDS = [
    IngestField("title", "str", "название задачи/проекта", required=True),
    IngestField("status", "enum", "статус выполнения", enum=TASK_STATUS),
    IngestField("priority", "enum", "приоритет", enum=PRIORITY),
    IngestField("due_date", "date", "срок (дедлайн), YYYY-MM-DD"),
    IngestField("direction", "str", "направление/категория — из справочника направлений"),
]


TARGETS: list[IngestTarget] = [
    IngestTarget(
        key="projects_tasks",
        label="Проекты и задачи",
        when="документ содержит перечень проектов, задач, мероприятий, поручений, "
             "планов работ с названиями, статусами, сроками, ответственными",
        fields=_TASK_FIELDS,
        supported=True,
        nests_tasks=True,
    ),
    # ── ниже: дашборды, которые агент УЖЕ распознаёт, но авто-создание
    #    пока не подключено (supported=False) — отдаём распознанные строки на превью.
    IngestTarget(
        key="kpi",
        label="KPI (ключевые показатели)",
        when="таблица показателей с планом/фактом, единицами измерения, целевыми значениями по периодам",
        fields=[
            IngestField("company", "str", "предприятие", required=True),
            IngestField("indicator", "str", "название показателя", required=True),
            IngestField("unit", "str", "единица измерения"),
            IngestField("weight", "number", "вес показателя (если есть)"),
            IngestField("plan", "number", "плановое значение"),
            IngestField("fact", "number", "фактическое значение"),
            IngestField("period", "str", "период (год/квартал/месяц)"),
        ],
        supported=True,
    ),
    IngestTarget(
        key="financials",
        label="Финансовая отчётность",
        when="статьи отчётности (P&L / баланс / денежный поток), суммы, валюта, стандарт МСФО или НСБУ",
        fields=[
            IngestField("company", "str", "предприятие", required=True),
            IngestField("article", "str", "статья отчётности (наименование строки)", required=True),
            IngestField("value", "number", "сумма"),
            IngestField("report_type", "enum", "тип отчёта: PL=ОПУ, BS=баланс, CF=денежный поток", enum=["PL", "BS", "CF"]),
            IngestField("standard", "enum", "стандарт", enum=["IFRS", "NSBU"]),
            IngestField("year", "int", "год отчёта"),
            IngestField("currency", "enum", "валюта", enum=["UZS", "USD", "EUR"]),
        ],
        supported=True,
    ),
    IngestTarget(
        key="ratings",
        label="Рейтинги",
        when="оценки/баллы предприятий по критериям с весами, скоринг",
        fields=[
            IngestField("company", "str", "предприятие", required=True),
            IngestField("criterion", "str", "критерий оценки", required=True),
            IngestField("score", "number", "балл"),
            IngestField("weight", "number", "вес критерия"),
            IngestField("period", "str", "период"),
        ],
    ),
    IngestTarget(
        key="credit_portfolio",
        label="Кредитный портфель",
        when="кредиты/займы: номер, кредитор, сумма основного долга, ставка, срок погашения",
        fields=[
            IngestField("company", "str", "заёмщик (предприятие)", required=True),
            IngestField("loan_no", "str", "номер кредита/договора"),
            IngestField("creditor", "str", "кредитор/банк"),
            IngestField("principal", "number", "основной долг"),
            IngestField("currency", "enum", "валюта", enum=["UZS", "USD", "EUR"]),
            IngestField("rate", "number", "процентная ставка"),
            IngestField("maturity", "date", "дата погашения"),
        ],
    ),
    IngestTarget(
        key="invest_projects",
        label="Инвестпроекты (CAPEX)",
        when="капитальные объекты/инвестпроекты: бюджет, стадия, процент готовности, срок ввода",
        fields=[
            IngestField("company", "str", "предприятие", required=True),
            IngestField("object", "str", "название объекта/проекта", required=True),
            IngestField("budget", "number", "бюджет CAPEX"),
            IngestField("stage", "str", "стадия"),
            IngestField("completion", "number", "процент готовности"),
            IngestField("deadline", "date", "срок ввода"),
        ],
    ),
    IngestTarget(
        key="procurement",
        label="Закупки",
        when="закупки/поставки: поставщик, позиция, количество, цена за единицу, сумма, дата",
        fields=[
            IngestField("supplier", "str", "поставщик", required=True),
            IngestField("item", "str", "позиция/товар", required=True),
            IngestField("qty", "number", "количество"),
            IngestField("unit_price", "number", "цена за единицу"),
            IngestField("total", "number", "сумма"),
            IngestField("date", "date", "дата"),
        ],
    ),
    IngestTarget(
        key="esg",
        label="ESG-метрики",
        when="экологические/социальные/управленческие метрики: выбросы, энергия, кадры, охрана труда",
        fields=[
            IngestField("company", "str", "предприятие", required=True),
            IngestField("metric", "str", "метрика", required=True),
            IngestField("value", "number", "значение"),
            IngestField("unit", "str", "единица измерения"),
            IngestField("category", "enum", "категория", enum=["E", "S", "G"]),
            IngestField("period", "str", "период"),
        ],
    ),
    IngestTarget(
        key="governance",
        label="Корпоративное управление",
        when="вопросы/решения корпуправления: пункт, статус, ответственный, срок",
        fields=[
            IngestField("company", "str", "предприятие", required=True),
            IngestField("item", "str", "пункт/вопрос", required=True),
            IngestField("status", "str", "статус"),
            IngestField("responsible", "str", "ответственный"),
            IngestField("deadline", "date", "срок"),
        ],
    ),
]

BY_KEY = {t.key: t for t in TARGETS}


def target_catalog_for_prompt() -> str:
    """Текстовое описание реестра целей для системного промпта классификатора."""
    lines: list[str] = []
    for t in TARGETS:
        flag = "✓ авто-создание" if t.supported else "распознавание (превью)"
        lines.append(f"- key=\"{t.key}\" — {t.label} [{flag}]")
        lines.append(f"    когда: {t.when}")
        cols = ", ".join(
            f"{f.name}" + (f"({'|'.join(f.enum)})" if f.enum else "")
            for f in t.fields
        )
        lines.append(f"    поля: {cols}")
    return "\n".join(lines)


def fields_meta(key: str) -> list[dict]:
    """Схема полей цели для превью на фронте (заголовки таблицы)."""
    t = BY_KEY.get(key)
    if not t:
        return []
    return [{"name": f.name, "type": f.type, "desc": f.desc, "enum": f.enum} for f in t.fields]
