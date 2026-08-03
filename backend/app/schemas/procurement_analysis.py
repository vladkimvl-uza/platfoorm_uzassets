"""Procurement Analysis schemas — types for the BETA tab «Анализ закупочной деятельности».

Mirrors the legacy `paCompute()` aggregation 1:1.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# 2026-05-26: MoneyDecimal сериализует Decimal как float в JSON, чтобы
# frontend получал числа а не строки (см. _types.py rationale).
from app.schemas._types import MoneyDecimal

# =====================================================================
# Closure (purchase / contract)
# =====================================================================

class ClosureRow(BaseModel):
    """A single procurement closure (контракт / закупка) row."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    company_name: Optional[str] = None
    company_color: Optional[str] = None
    company_sector: Optional[str] = None

    category_id: Optional[str] = None
    category_name: Optional[str] = None
    category_unit: Optional[str] = None        # ед. измерения

    product_code: Optional[str] = None         # KTRU code
    sub_product_code: Optional[str] = None     # cluster code (after price clustering)
    product_name: Optional[str] = None
    product_type: Optional[str] = None         # 'PRODUCT' | 'SERVICE' (товар / услуга)

    supplier: Optional[str] = None
    supplier_inn: Optional[str] = None
    unit_price: MoneyDecimal
    market_avg: MoneyDecimal                    # benchmark median for the cluster
    volume: MoneyDecimal

    deviation_pct: float                        # (unit_price - market_avg) / market_avg * 100
    deviation_abs: Optional[MoneyDecimal] = None  # absolute UZS overpayment

    spread_pct: Optional[float] = None          # cluster spread for QC
    is_dirty: bool = False                      # excluded from KPI aggregates

    contract_date: Optional[date] = None
    year: Optional[int] = None

    # Заключение центра экспертизы (заполняется вручную, по каждой закупке)
    conclusion_text: Optional[str] = None
    conclusion_status: Optional[str] = None
    conclusion_date: Optional[datetime] = None
    conclusion_author_name: Optional[str] = None


# =====================================================================
# Per-category deviation (within a company)
# =====================================================================

class CategoryDeviation(BaseModel):
    """A single category's deviation within a company's procurement."""
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    category_short: Optional[str] = None
    sum_dev: MoneyDecimal                            # absolute overpayment in UZS
    sum_ref: MoneyDecimal                            # benchmark spend
    deviation_pct: float                        # weighted-avg deviation
    closure_count: int


# =====================================================================
# Company rating row
# =====================================================================

class CompanyRatingRow(BaseModel):
    """One company's row in the rating table.

    Mirrors legacy `co` object in `paCompute().rating[]`.
    """
    company_id: UUID
    company_code: Optional[str] = None
    company_name: str
    company_color: Optional[str] = None
    company_sector: Optional[str] = None

    # None = сопоставимых позиций нет. Раньше такие компании добавлялись в
    # рейтинг с отклонением 0.00% и вставали в один ряд с реально измеренными.
    company_deviation: Optional[float] = None   # weighted-avg deviation %
    has_comparable: bool = True                 # есть ли база для отклонения
    sum_dev: MoneyDecimal                             # net overpayment (can be negative for savings)
    sum_ref: MoneyDecimal                             # benchmark spend
    above_count: int                             # red closures count (dev ≥ +10%)
    cat_count: int                               # # categories with data
    cat_dev: list[CategoryDeviation] = Field(default_factory=list)

    best_cats: list[CategoryDeviation] = Field(default_factory=list)   # top-3 negative dev
    worst_cats: list[CategoryDeviation] = Field(default_factory=list)  # top-3 positive dev

    # legacy-compat fields (PaRatingPanel + PaLeaders ожидают эти)
    sum_overpay: MoneyDecimal = Decimal(0)       # Σ(positive deviations) — for sort
    sum_savings: MoneyDecimal = Decimal(0)       # Σ(negative deviations as positive)
    red_pct: Optional[float] = None               # % closures with dev ≥ +10%
    yellow_pct: Optional[float] = None            # % closures with dev 0..+10%
    green_pct: Optional[float] = None             # % closures with dev < 0
    problem_cats: int = 0                         # # categories where avg dev > 10%
    total_count: int = 0                          # total non-dirty closures count
    low_sample: bool = False                       # мало сопоставимых позиций → company_deviation недостоверно

    # Совокупный расход компании (лот-дедуп, ВСЕ типы) + разбивка — для шапки профиля.
    # Это НЕ sum_ref (тот = только сопоставимый товарный benchmark для отклонения).
    company_total_spend: MoneyDecimal = Decimal(0)
    goods_spend: MoneyDecimal = Decimal(0)        # товары (PRODUCT)
    services_spend: MoneyDecimal = Decimal(0)     # услуги (SERVICE)
    works_spend: MoneyDecimal = Decimal(0)        # работы (WORK)
    total_lots: int = 0                            # уникальных лотов компании

    rank: int = 0


# =====================================================================
# Category metadata (the 15 fixed categories)
# =====================================================================

class CategoryMeta(BaseModel):
    """One of the 15 procurement categories (fixed list)."""
    id: int
    name: str
    short: str
    icon: Optional[str] = None
    unit: str = "ед"                            # default unit


# =====================================================================
# Product-level aggregation (contracts mode — used by PaCategoryGrid
# and PaPainPoints. Mirrors legacy data.productsByCode + cat.allProducts.)
# =====================================================================

class ProductAgg(BaseModel):
    code: str                                   # productCode (KTRU)
    root_code: str                              # KTRU root before "-XXXXX"
    name: str
    unit: str
    product_type: str = "PRODUCT"               # 'PRODUCT' | 'SERVICE'
    category_id: Optional[str] = None
    avg_price: float                            # median of band (in-band) effective prices
    min_price: float
    max_price: float
    spread_pct: float                           # (max-min) / min * 100 ПО ПОЛОСЕ сопоставимости
    full_spread_pct: float = 0.0                 # полный разброс по всем эфф.ценам (для плашки «грязный»)
    total_spend: float                          # Σ unit_price * volume
    unique_buyers: int                          # unique company_id count
    contract_count: int
    max_deviation_pct: float                    # max |unit_price - market_avg| / market_avg * 100
    quality_band: str = "clean"                 # 'clean' | 'wide' | 'dirty'
    cluster_index: int = 0
    total_clusters: int = 1
    cluster_label: str = ""
    # Потенциальная экономия по коду: Σ volume×(price − лучшая сопоставимая цена)
    # в полосе [медиана×0.5 … ×2]. Считается только для сопоставимых (>=2 покупателя).
    potential_saving: float = 0.0
    total_volume: float = 0.0


class CategoryAggregate(BaseModel):
    """Per-category aggregation (extends CategoryMeta with computed fields)."""
    id: int
    name: str
    short: str
    unit: str = "ед"
    all_products: list[ProductAgg] = Field(default_factory=list)
    clean_count: int = 0
    benchmark_product_count: int = 0
    clean_spread_min: Optional[float] = None
    clean_spread_max: Optional[float] = None


class ProcurementMeta(BaseModel):
    source: str                                 # 'procurementContracts' | 'priceListLegacy'


# =====================================================================
# Supplier / method / platform breakdowns (lot-deduplicated spend)
# =====================================================================

class SupplierAgg(BaseModel):
    """Один поставщик. Спенд лот-дедуплицирован (одна сумма на lotId)."""
    supplier_inn: Optional[str] = None
    supplier_name: str
    spend: MoneyDecimal                          # Σ contract_amount по уникальным лотам
    spend_share_pct: float = 0.0                 # доля от совокупного спенда
    lot_count: int = 0
    company_count: int = 0                        # скольким SOE поставляет
    company_codes: list[str] = Field(default_factory=list)
    saved_amount: MoneyDecimal = Decimal(0)
    saved_rate_pct: float = 0.0                   # экономия на торгах = saved / start
    is_cross: bool = False                        # снабжает >=2 компаний
    # «дороговизна»: цена выше медианы рынка по сопоставимым кодам
    excess_uzs: MoneyDecimal = Decimal(0)         # Σ переплаты над медианой
    comparable_spend: MoneyDecimal = Decimal(0)   # спенд по сопоставимым позициям
    premium_pct: float = 0.0                      # excess / comparable_spend × 100
    overpriced_lines: int = 0


class SupplierConcentration(BaseModel):
    """Концентрация поставщиков внутри одной компании (зависимость/риск)."""
    company_id: UUID
    company_name: str
    company_color: Optional[str] = None
    company_sector: Optional[str] = None
    spend: MoneyDecimal
    supplier_count: int = 0
    top1_name: Optional[str] = None
    top1_pct: float = 0.0
    top3_pct: float = 0.0
    hhi: float = 0.0                              # 0..10000 (индекс Херфиндаля)


class MethodAgg(BaseModel):
    """Разрез по способу закупки (purchase_type), лот-дедуп."""
    method: str                                  # нормализованный ключ
    label: str                                   # человекочитаемо
    lot_count: int = 0
    spend: MoneyDecimal
    spend_share_pct: float = 0.0
    saved_amount: MoneyDecimal = Decimal(0)
    saved_rate_pct: float = 0.0                   # ставка экономии = saved / start
    is_competitive: bool = False                 # торг был (не каталог)


class PlatformAgg(BaseModel):
    """Разрез по электронной площадке (platform), лот-дедуп."""
    platform: str
    lot_count: int = 0
    spend: MoneyDecimal
    spend_share_pct: float = 0.0
    saved_amount: MoneyDecimal = Decimal(0)
    saved_rate_pct: float = 0.0


class WorkServiceByCompany(BaseModel):
    """Разовые услуги и работы (несравнимые по цене за единицу) — по компаниям."""
    company_id: UUID
    company_name: str
    company_color: Optional[str] = None
    company_sector: Optional[str] = None
    services_spend: MoneyDecimal = Decimal(0)    # SERVICE
    services_lots: int = 0
    works_spend: MoneyDecimal = Decimal(0)       # WORK
    works_lots: int = 0
    total_spend: MoneyDecimal = Decimal(0)       # услуги + работы


# =====================================================================
# Aggregate response (the BETA tab payload)
# =====================================================================

class ProcurementKpis(BaseModel):
    total_companies: int
    clean_companies: int                         # companies with at least 1 clean closure
    total_closures: int
    clean_closures: int                          # closures excluding `is_dirty`
    total_overpay_uzs: MoneyDecimal              # sum of positive deviations
    # None = ни у одной компании нет сопоставимых позиций → судить не о чем
    above_market_pct: Optional[float] = None     # % companies with avg deviation > 0
    median_deviation_pct: Optional[float] = None # portfolio-wide median
    # ── расширение (лот-дедуплицированные деньги) ──
    total_spend: MoneyDecimal = Decimal(0)       # совокупный расход (одна сумма на лот)
    total_lots: int = 0                          # уникальных лотов
    saved_amount: MoneyDecimal = Decimal(0)      # уже сэкономлено на торгах
    # None = экономия не указана в источнике ни у одного лота. Ноль здесь означал
    # бы «торговались и не сэкономили» — это разные вещи, и на проде у всех
    # 5 947 лотов e_shop (24% спенда) поля экономии нет как класса.
    saved_rate_pct: Optional[float] = None       # saved / start, только по лотам с известной экономией
    saving_known_lots: int = 0                   # у скольких лотов экономия вообще указана
    saving_known_spend: MoneyDecimal = Decimal(0)
    saving_unknown_spend: MoneyDecimal = Decimal(0)
    no_tender_spend: MoneyDecimal = Decimal(0)   # спенд НЕКОНКУРЕНТНЫХ методов (e_shop/каталог/пусто)
    no_tender_pct: Optional[float] = None         # доля спенда без конкурентной процедуры
    # Считается ТОЛЬКО по лотам, где экономия известна и равна нулю. Раньше сюда
    # попадали лоты с неизвестной экономией — отсутствие данных подавалось как
    # признак имитации торга.
    competitive_no_saving_spend: MoneyDecimal = Decimal(0)
    competitive_no_saving_pct: Optional[float] = None
    potential_saving_uzs: MoneyDecimal = Decimal(0)  # Σ потенц. экономии по товарам
    supplier_count: int = 0                      # раскрытых поставщиков
    disclosed_supplier_pct: Optional[float] = None  # доля спенда с раскрытым поставщиком
    cross_supplier_pct: float = 0.0              # доля спенда у сквозных поставщиков (по ВСЕМ, не топ-50)
    services_spend: MoneyDecimal = Decimal(0)    # спенд на услуги (productType=SERVICE)
    services_pct: Optional[float] = None         # доля услуг в спенде
    goods_spend: MoneyDecimal = Decimal(0)       # спенд на товары (productType=PRODUCT)
    works_spend: MoneyDecimal = Decimal(0)       # спенд на работы (productType=WORK)
    works_pct: Optional[float] = None            # доля работ в спенде


class ProcurementCoverage(BaseModel):
    """Честный знаменатель экрана: по какой части данных считаются цифры.

    Появился по итогам замера: ключевые «денежные» метрики строятся на 7–8%
    спенда (сопоставимые пары), экономия известна у 12% лотов, категория — у
    55% строк, а весь массив — это один квартал одного года. Без этих чисел
    экран выглядел как полная картина закупок портфеля.
    """
    companies_total: int = 0            # компаний в области видимости
    companies_with_data: int = 0        # из них с закупками
    companies_comparable: int = 0       # из них с сопоставимыми позициями
    closures_total: int = 0             # строк закупок
    lots_total: int = 0                 # уникальных лотов
    spend_total: MoneyDecimal = Decimal(0)
    comparable_spend: MoneyDecimal = Decimal(0)   # спенд, покрытый сопоставимыми позициями
    comparable_spend_pct: Optional[float] = None
    saving_known_lots_pct: Optional[float] = None  # доля лотов с известной экономией
    category_known_pct: Optional[float] = None     # доля строк с категорией
    supplier_known_pct: Optional[float] = None     # доля спенда с раскрытым поставщиком
    period_from: Optional[str] = None    # первая дата закрытия в выборке
    period_to: Optional[str] = None      # последняя
    years: list[int] = Field(default_factory=list)  # какие годы вообще есть


class ProcurementAggregate(BaseModel):
    """Top-level response of /procurement/aggregate.

    Mirrors legacy `paCompute()` output 1:1.
    """
    year: Optional[int] = None
    sector_code: Optional[str] = None

    # False → данных для экрана нет вовсе; фронт обязан показать пустое
    # состояние, а не полосу нулей.
    has_data: bool = True
    coverage: ProcurementCoverage = Field(default_factory=ProcurementCoverage)

    kpis: ProcurementKpis
    categories: list[CategoryMeta] = Field(default_factory=list)
    category_aggregates: list[CategoryAggregate] = Field(default_factory=list)
    products_by_code: dict[str, ProductAgg] = Field(default_factory=dict)
    rating: list[CompanyRatingRow] = Field(default_factory=list)
    purchases: list[ClosureRow] = Field(default_factory=list)

    # ── разрезы по поставщикам / способам / площадкам ──
    suppliers_top: list[SupplierAgg] = Field(default_factory=list)        # топ по спенду
    suppliers_cross: list[SupplierAgg] = Field(default_factory=list)     # сквозные (>=2 компаний)
    suppliers_expensive: list[SupplierAgg] = Field(default_factory=list) # дорогие (премия к рынку)
    supplier_concentration: list[SupplierConcentration] = Field(default_factory=list)
    methods: list[MethodAgg] = Field(default_factory=list)
    platforms: list[PlatformAgg] = Field(default_factory=list)
    works_services: list[WorkServiceByCompany] = Field(default_factory=list)

    available_years: list[int] = Field(default_factory=list)
    sectors: list[dict[str, str]] = Field(default_factory=list)   # [{code, label}]
    meta: ProcurementMeta = Field(default_factory=lambda: ProcurementMeta(source="procurementContracts"))
    generated_at: datetime
