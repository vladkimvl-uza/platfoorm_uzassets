"""Canonical line schemas for detailed МСФО reports.

Each report type (BS / PL / CF) has a fixed set of "canonical lines" that
all 22 companies should report on. When parsing an Excel file, we match
each detected row's label against these canonical lines using fuzzy
matching (slugified label + alias list). This lets us:

  • Detect rows that don't correspond to any canonical line ("unmapped")
    and flag them in the UI for manual review.
  • Detect missing canonical lines a company should have but didn't report.
  • Render a consistent, comparable grid across all 22 companies.

The schema is built from NGMK as the baseline (the most complete sheet
in the High_Level_Financials_v4 file), with manually added aliases
covering the variations seen in UMK / UTY / TST / NUR and other sheets.

NOTE on duplicate labels (e.g. "Inventories" appears in both Non-current
and Current assets): the canonical code is disambiguated by section
(e.g. `inventories_nc`, `inventories_cur`). Section detection in the
parser determines which canonical line a duplicate label maps to.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CanonicalLine:
    code: str                              # Stable canonical code (e.g. "ppe")
    label: str                             # Display label (English)
    label_ru: Optional[str] = None         # Russian display
    section: Optional[str] = None          # Group header (Non-current assets, etc.)
    section_alt: list[str] = field(default_factory=list)  # Alt section names that map here
    indent: int = 0
    is_subtotal: bool = False
    aliases: list[str] = field(default_factory=list)  # Alt labels to match (slugified)


# ── Helpers ─────────────────────────────────────────────────────────────


def _slug(text: str) -> str:
    """Normalize text for fuzzy matching: lowercase, strip non-alphanumeric, collapse spaces."""
    if not text:
        return ""
    s = re.sub(r"[^\w\s]", " ", text.lower(), flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _section_match(detected: Optional[str], canonical_section: Optional[str], alts: list[str]) -> bool:
    """Compare a detected section header against the canonical's expected section.

    Match is TOKEN-EQUALITY based (case/punctuation insensitive). This is
    the only way to correctly distinguish "Current liabilities" from
    "Non-current liabilities" — a substring or subset match would wrongly
    treat them as equivalent.

    For non-English headers (e.g. Russian "Краткосрочные обязательства"),
    the canonical's `section_alt` list is consulted.
    """
    if not canonical_section:
        return True
    if not detected:
        return True

    d_tokens = set(_slug(detected).split())

    def _matches(target: str) -> bool:
        t_tokens = set(_slug(target).split())
        return bool(t_tokens) and t_tokens == d_tokens

    if _matches(canonical_section):
        return True
    for alt in alts:
        if _matches(alt):
            return True
    return False


# ── Canonical schemas ───────────────────────────────────────────────────

# Statement of Financial Position
BS_CANONICAL: list[CanonicalLine] = [
    # Non-current assets
    CanonicalLine("ppe", "Property, plant and equipment", "Основные средства",
                  section="Non-current assets",
                  section_alt=["Внеоборотные активы", "Узоқ муддатли активлар", "Долгосрочные активы"],
                  aliases=["property plant and equipment", "ppe",
                           "основные средства", "ОС", "fixed assets", "tangible fixed assets",
                           "amortizatsiyani amortizatsiya"]),
    CanonicalLine("intangible_assets", "Intangible assets", "Нематериальные активы",
                  section="Non-current assets",
                  aliases=["intangible assets", "нематериальные активы", "intangibles"]),
    CanonicalLine("right_of_use_assets", "Right-of-use assets",
                  section="Non-current assets",
                  aliases=["right of use assets", "right-of-use assets",
                           "активы в форме права пользования"]),
    CanonicalLine("exploration_and_evaluation", "Exploration and evaluation assets",
                  section="Non-current assets",
                  aliases=["exploration and evaluation", "exploration and evaluation assets",
                           "поисковые и оценочные активы"]),
    CanonicalLine("investments_in_jv", "Investments in joint ventures and associates",
                  section="Non-current assets",
                  aliases=["investments in joint ventures and associates",
                           "investments in joint ventures",
                           "investments in associates",
                           "investments in associates and joint ventures",
                           "инвестиции в совместные и ассоциированные предприятия",
                           "инвестиции в ассоциированные и совместные предприятия"]),
    CanonicalLine("other_investments", "Other investments",
                  section="Non-current assets",
                  aliases=["other investments", "прочие инвестиции",
                           "инвестиции имеющиеся в наличии для продажи",
                           "available for sale investments"]),
    CanonicalLine("loans_issued", "Loans issued",
                  section="Non-current assets",
                  aliases=["loans issued", "выданные займы"]),
    CanonicalLine("investment_property", "Investment property",
                  section="Non-current assets",
                  aliases=["investment property", "инвестиционная недвижимость"]),
    CanonicalLine("deferred_tax_assets", "Deferred tax assets",
                  section="Non-current assets",
                  aliases=["deferred tax assets", "отложенные налоговые активы"]),
    CanonicalLine("inventories_nc", "Inventories (non-current)", "Запасы (долгосрочные)",
                  section="Non-current assets",
                  aliases=["inventories", "запасы", "zaxiralar"]),
    CanonicalLine("trade_receivables_nc", "Trade and other receivables (non-current)",
                  section="Non-current assets",
                  aliases=["trade and other receivables", "long-term receivables",
                           "долгосрочная дебиторская задолженность"]),
    CanonicalLine("advances_for_nca", "Advances for non-current assets",
                  section="Non-current assets",
                  aliases=["advances for non-current assets", "advances for non current assets",
                           "advances paid for acquisition of non-current assets",
                           "авансы за внеоборотные активы"]),
    CanonicalLine("other_nc_assets", "Other non-current assets",
                  section="Non-current assets",
                  aliases=["other non-current assets", "other non current assets",
                           "investment projects",
                           "прочие внеоборотные активы", "прочие долгосрочные активы",
                           "прочие долгосрочные расходы",
                           "прочие долгосрочные финансовые активы", "other"]),
    CanonicalLine("total_nc_assets", "Total non-current assets",
                  section="Non-current assets",
                  is_subtotal=True,
                  aliases=["total non-current assets", "total non current assets",
                           "non-current assets", "non current assets",
                           "итого внеоборотные активы", "узоқ муддатли активлар", "итого"]),

    # Current assets
    CanonicalLine("inventories_cur", "Inventories", "Запасы",
                  section="Current assets",
                  section_alt=["Оборотные активы", "Жорий активлар"],
                  aliases=["inventories", "запасы", "zaxiralar"]),
    CanonicalLine("advances_paid", "Advances paid",
                  section="Current assets",
                  aliases=["advances paid", "выплаченные авансы", "авансы выданные",
                           "прочие выданные авансы", "prepayments"]),
    CanonicalLine("income_tax_prepaid", "Income tax prepaid",
                  section="Current assets",
                  aliases=["income tax prepaid", "prepaid income tax",
                           "current income tax prepayments",
                           "corporate income tax prepayment",
                           "переплата по налогу на прибыль",
                           "предоплата по текущему налогу на прибыль"]),
    CanonicalLine("other_taxes_receivable", "Other taxes receivable",
                  section="Current assets",
                  aliases=["other taxes receivable", "other tax receivable",
                           "prepaid taxes other than income tax",
                           "авансовые платежи по налогам и платежам"]),
    CanonicalLine("trade_receivables_cur", "Trade and other receivables",
                  section="Current assets",
                  aliases=["trade and other receivables", "trade receivables",
                           "торговая и прочая дебиторская задолженность",
                           "trade and other receivable"]),
    CanonicalLine("contract_assets", "Contract assets",
                  section="Current assets",
                  aliases=["contract assets", "активы по договорам"]),
    CanonicalLine("bank_deposits", "Bank deposits",
                  section="Current assets",
                  aliases=["bank deposits", "банковские депозиты"]),
    CanonicalLine("restricted_cash", "Restricted cash",
                  section="Current assets",
                  aliases=["restricted cash", "ограниченные денежные средства"]),
    CanonicalLine("cce", "Cash and cash equivalents", "Денежные средства и эквиваленты",
                  section="Current assets",
                  aliases=["cash and cash equivalents", "cash equivalents", "cash",
                           "денежные средства и их эквиваленты", "нақд пул"]),
    CanonicalLine("short_term_investments", "Short-term investments",
                  section="Current assets",
                  aliases=["short-term investments", "short term investments",
                           "краткосрочные инвестиции"]),
    CanonicalLine("other_cur_assets", "Other current assets",
                  section="Current assets",
                  aliases=["other current assets", "прочие оборотные активы"]),
    CanonicalLine("total_cur_assets", "Total current assets",
                  section="Current assets",
                  is_subtotal=True,
                  aliases=["total current assets", "current assets",
                           "итого оборотные активы", "жорий активлар"]),

    CanonicalLine("total_assets", "TOTAL ASSETS", "ИТОГО АКТИВЫ",
                  is_subtotal=True,
                  aliases=["total assets", "итого активы", "жами активлар"]),

    # Equity
    CanonicalLine("share_capital", "Share capital", "Уставный капитал",
                  section="Equity",
                  section_alt=["Капитал", "Собственный капитал"],
                  aliases=["share capital", "share cap", "уставный капитал", "issued capital",
                           "акционерный капитал"]),
    CanonicalLine("additional_paid_in", "Additional paid-in capital",
                  section="Equity",
                  aliases=["additional paid-in capital", "additional paid in capital",
                           "additional capital", "share premium",
                           "дополнительный оплаченный капитал"]),
    CanonicalLine("translation_reserve", "Translation reserve",
                  section="Equity",
                  aliases=["translation reserve", "currency translation reserve",
                           "резерв переоценки валют"]),
    CanonicalLine("other_reserves", "Other reserves",
                  section="Equity",
                  aliases=["other reserves", "reserves", "прочие резервы", "резервы",
                           "резерв по обесценению",
                           "treasury shares", "additional capital",
                           "share premium"]),
    CanonicalLine("retained_earnings", "Retained earnings", "Нераспределённая прибыль",
                  section="Equity",
                  aliases=["retained earnings", "нераспределённая прибыль",
                           "нераспределенная прибыль", "accumulated earnings",
                           "accumulated deficit", "накопленный убыток"]),
    CanonicalLine("equity_attributable_shareholder", "Equity attributable to shareholder",
                  section="Equity", is_subtotal=True,
                  aliases=["equity attributable to shareholder",
                           "equity attributable to shareholders",
                           "капитал акционеров"]),
    CanonicalLine("targeted_receipts", "Targeted receipts",
                  section="Equity",
                  aliases=["targeted receipts", "целевые поступления"]),
    CanonicalLine("nci", "Non-controlling interest",
                  section="Equity",
                  aliases=["non-controlling interest", "non-controlling interests",
                           "nci", "minority interest",
                           "неконтролирующая доля участия"]),
    CanonicalLine("total_equity", "TOTAL EQUITY", "ИТОГО КАПИТАЛ",
                  section="Equity",
                  is_subtotal=True,
                  aliases=["total equity", "итого капитал", "капитал"]),

    # Non-current liabilities
    CanonicalLine("borrowings_nc", "Borrowings (non-current)",
                  section="Non-current liabilities",
                  section_alt=["Долгосрочные обязательства", "Узоқ муддатли мажбуриятлар"],
                  aliases=["borrowings", "long-term borrowings", "loans and borrowings",
                           "loans and borrowins", "долгосрочные займы", "долгосрочные кредиты",
                           "кредиты и займы", "qarzlar"]),
    CanonicalLine("lease_liabilities_nc", "Lease liabilities (non-current)",
                  section="Non-current liabilities",
                  aliases=["lease liabilities", "обязательства по аренде"]),
    CanonicalLine("employee_benefits", "Employee benefits",
                  section="Non-current liabilities",
                  aliases=["employee benefits", "обязательства по вознаграждениям работникам"]),
    CanonicalLine("environmental_obligations", "Environmental obligations",
                  section="Non-current liabilities",
                  aliases=["environmental obligations", "природоохранные обязательства"]),
    CanonicalLine("provisions_nc", "Provisions",
                  section="Non-current liabilities",
                  aliases=["provisions", "резервы предстоящих расходов"]),
    CanonicalLine("deferred_tax_liabilities", "Deferred tax liabilities",
                  section="Non-current liabilities",
                  aliases=["deferred tax liabilities", "deferred tax",
                           "отложенные налоговые обязательства"]),
    CanonicalLine("other_nc_liabilities", "Other non-current liabilities",
                  section="Non-current liabilities",
                  aliases=["other non-current liabilities", "other long-term liabilities",
                           "прочие долгосрочные обязательства", "other"]),
    CanonicalLine("total_nc_liabilities", "Total non-current liabilities",
                  section="Non-current liabilities",
                  is_subtotal=True,
                  aliases=["total non-current liabilities", "non-current liabilities",
                           "итого долгосрочные обязательства"]),

    # Current liabilities
    CanonicalLine("borrowings_cur", "Borrowings (current)",
                  section="Current liabilities",
                  section_alt=["Краткосрочные обязательства", "Қисқа муддатли мажбуриятлар"],
                  aliases=["borrowings", "short-term borrowings", "loans and borrowings",
                           "loans and borrowins", "краткосрочные займы",
                           "кредиты и займы", "qarzlar",
                           "текущая часть долгосрочных обязательств",
                           "current portion of long-term debt"]),
    CanonicalLine("trade_payables", "Trade and other payables",
                  section="Current liabilities",
                  aliases=["trade and other payables", "trade payables",
                           "торговая и прочая кредиторская задолженность"]),
    CanonicalLine("contract_liabilities", "Contract liabilities",
                  section="Current liabilities",
                  aliases=["contract liabilities", "обязательства по договорам с покупателями"]),
    CanonicalLine("advances_received", "Advances received",
                  section="Current liabilities",
                  aliases=["advances received", "полученные авансы"]),
    CanonicalLine("income_tax_payable", "Income tax payable",
                  section="Current liabilities",
                  aliases=["income tax payable",
                           "обязательства по текущему налогу на прибыль",
                           "current income tax payable"]),
    CanonicalLine("other_taxes_payable", "Other taxes payable",
                  section="Current liabilities",
                  aliases=["other taxes payable", "tax payables", "налоги к уплате",
                           "текущее обязательство по налогам и внебюджетным фондам"]),
    CanonicalLine("lease_liabilities_cur", "Lease liabilities (current)",
                  section="Current liabilities",
                  aliases=["lease liabilities", "обязательства по аренде"]),
    CanonicalLine("other_cur_liabilities", "Other current liabilities",
                  section="Current liabilities",
                  aliases=["other current liabilities",
                           "прочие краткосрочные обязательства", "other"]),
    CanonicalLine("total_cur_liabilities", "Total current liabilities",
                  section="Current liabilities",
                  is_subtotal=True,
                  aliases=["total current liabilities", "current liabilities",
                           "итого краткосрочные обязательства"]),

    CanonicalLine("total_liabilities", "Total liabilities",
                  is_subtotal=True,
                  aliases=["total liabilities", "итого обязательства"]),
    CanonicalLine("total_equity_and_liabilities", "Total equity and liabilities",
                  is_subtotal=True,
                  aliases=["total equity and liabilities", "итого капитал и обязательства",
                           "total liabilities and equity"]),
]


# Profit & Loss
PL_CANONICAL: list[CanonicalLine] = [
    CanonicalLine("revenue", "Revenue", "Выручка",
                  aliases=["revenue", "выручка", "тушум", "sales", "net sales"]),
    CanonicalLine("cos", "Cost of sales", "Себестоимость",
                  aliases=["cost of sales", "cos", "cogs", "cost of goods sold",
                           "себестоимость", "таннарх"]),
    CanonicalLine("consumables", "Consumables and spares",
                  aliases=["consumables and spares", "consumables", "запасные части и материалы"]),
    CanonicalLine("royalty", "Royalty (Mineral extraction tax)",
                  aliases=["royalty", "mineral extraction tax", "royalty mineral extraction tax",
                           "налог за пользование недрами"]),
    CanonicalLine("labour", "Labour cost",
                  aliases=["labour", "labour cost", "labor", "wages and salaries", "оплата труда"]),
    CanonicalLine("depreciation_pl", "Depreciation and amortisation",
                  aliases=["depreciation and amortisation", "depreciation and amortization",
                           "depreciation", "d a", "амортизация"]),
    CanonicalLine("utilities", "Utilities",
                  aliases=["utilities", "коммунальные услуги"]),
    CanonicalLine("fuel", "Fuel",
                  aliases=["fuel", "топливо"]),
    CanonicalLine("change_in_wip", "Change in work in progress and finished goods",
                  aliases=["change in work in progress and finished goods",
                           "change in wip", "изменение нзп и готовой продукции"]),
    CanonicalLine("gross_profit", "Gross profit", "Валовая прибыль",
                  is_subtotal=True,
                  aliases=["gross profit", "валовая прибыль"]),
    CanonicalLine("admin_selling", "Administrative and selling expenses",
                  aliases=["administrative and selling expenses", "g a", "gna",
                           "selling expenses", "general and administrative expenses",
                           "administrative expenses",
                           "общие и административные расходы",
                           "административные и коммерческие расходы"]),
    CanonicalLine("other_op_income", "Other operating income",
                  aliases=["other operating income", "other income",
                           "gain from disposal of subsidiary",
                           "прочие операционные доходы", "прочие доходы"]),
    CanonicalLine("other_op_expense", "Other operating expense",
                  aliases=["other operating expense", "other expenses", "other",
                           "csr costs",
                           "impairment of tr and advances paid",
                           "прочие операционные расходы"]),
    CanonicalLine("operating_profit", "Operating profit", "Операционная прибыль",
                  is_subtotal=True,
                  aliases=["operating profit", "операционная прибыль", "ebit"]),
    CanonicalLine("finance_income", "Finance income",
                  aliases=["finance income", "fin income", "финансовые доходы",
                           "процентные доходы"]),
    CanonicalLine("finance_cost", "Finance cost",
                  aliases=["finance cost", "finance costs", "fin cost",
                           "interest", "interest expense",
                           "процентные расходы", "финансовые расходы",
                           "фоиз харажатлари"]),
    CanonicalLine("forex_pl", "Foreign exchange (loss) / gain",
                  aliases=["forex", "foreign exchange loss", "foreign exchange gain",
                           "fx loss", "fx gain", "forex net", "net fx loss",
                           "курсовая разница", "валюта курси фарқи"]),
    CanonicalLine("government_subsidies", "Income from government subsidies",
                  aliases=["income from government subsidies", "государственные субсидии"]),
    CanonicalLine("pbt", "Profit before income tax", "Прибыль до налогообложения",
                  is_subtotal=True,
                  aliases=["profit before income tax", "pbt", "прибыль до налогообложения"]),
    CanonicalLine("income_tax", "Income tax expense",
                  aliases=["income tax expense", "income tax", "tax", "income tax expense benefit",
                           "налог на прибыль", "фойда солиғи"]),
    CanonicalLine("current_tax", "Current tax expense",
                  aliases=["current tax expense", "текущий налог на прибыль"]),
    CanonicalLine("deferred_tax_pl", "Deferred tax expense",
                  aliases=["deferred tax expense", "deferred tax", "отложенный налог"]),
    CanonicalLine("net_income", "Profit / (loss) for the year", "Чистая прибыль / убыток",
                  is_subtotal=True,
                  aliases=["profit for the year", "net income", "net profit", "чистая прибыль",
                           "соф фойда", "net loss for the year", "net loss",
                           "profit loss for the year"]),
    CanonicalLine("oci", "Other comprehensive income/(loss) for the year, net of tax",
                  aliases=["other comprehensive loss for the year, net of tax",
                           "other comprehensive income for the year",
                           "other comprehensive income", "oci",
                           "прочий совокупный доход"]),
    CanonicalLine("total_comprehensive", "Total comprehensive income for the year",
                  is_subtotal=True,
                  aliases=["total comprehensive income for the year", "total comprehensive income",
                           "итого совокупный доход"]),
]


# Cash Flow
CF_CANONICAL: list[CanonicalLine] = [
    CanonicalLine("cf_pbt", "Profit / (loss) before income tax",
                  aliases=["pbt", "profit before tax", "profit before income tax",
                           "profit / (loss) before income tax",
                           "profit loss before income tax",
                           "прибыль до налогообложения",
                           "прибыль убыток до налогообложения"]),
    # Direct-method receipts/payments (TST CF format)
    CanonicalLine("cf_receipts_sales", "Receipts from customers",
                  section="Operating activities",
                  aliases=["receipts from customers",
                           "поступление от продажи товаров и услуг",
                           "поступления от покупателей"]),
    CanonicalLine("cf_payments_suppliers", "Payments to suppliers",
                  section="Operating activities",
                  aliases=["payments to suppliers",
                           "выплаты за полученные тмз и товары услуги",
                           "выплаты поставщикам"]),
    CanonicalLine("cf_payments_employees", "Payments to employees",
                  section="Operating activities",
                  aliases=["payments to employees",
                           "выплаты сотрудникам и от их имени"]),
    CanonicalLine("cf_other_op_receipts", "Other operating receipts/payments, net",
                  section="Operating activities",
                  aliases=["other operating receipts payments net",
                           "прочие поступления и выплаты в операционной деятельности чистые"]),
    CanonicalLine("cf_other_taxes_paid", "Other taxes paid",
                  aliases=["other taxes paid",
                           "выплаченные прочие налоги"]),
    CanonicalLine("cf_interest_received", "Interest received",
                  section="Investing activities",
                  aliases=["interest received",
                           "проценты полученные",
                           "проценты полученные выплаченные"]),
    CanonicalLine("cf_dividends_received", "Dividends received",
                  section="Investing activities",
                  aliases=["dividends received",
                           "дивиденды полученные",
                           "дивиденды полученные выплаченные"]),
    CanonicalLine("cf_depreciation", "Depreciation and amortisation",
                  section="Adjustments",
                  section_alt=["Adjustments:"],
                  aliases=["depreciation and amortisation", "depreciation",
                           "depreciation amortization",
                           "depreciation of ppe", "depreciation of ppe and intangible",
                           "амортизация", "амортизацию основных средств",
                           "амортизацию"]),
    CanonicalLine("cf_impairment", "Impairment charge",
                  section="Adjustments",
                  aliases=["impairment charge", "impairment", "обесценение"]),
    CanonicalLine("cf_loss_disposal_ppe", "Loss / (gain) on disposal of PPE",
                  section="Adjustments",
                  aliases=["loss on disposal of ppe", "loss on diposal of ppe",
                           "gain on disposal of ppe",
                           "убыток от выбытия ос"]),
    CanonicalLine("cf_finance_income", "Finance income",
                  section="Adjustments",
                  aliases=["finance income", "fin income",
                           "финансовые доходы", "проценты полученные",
                           "interest received"]),
    CanonicalLine("cf_finance_cost", "Finance cost",
                  section="Adjustments",
                  aliases=["finance cost", "finance costs", "fin cost", "interest expense",
                           "финансовые расходы"]),
    CanonicalLine("cf_forex", "Foreign exchange loss / (gain)",
                  section="Adjustments",
                  aliases=["foreign exchange loss", "forex", "forex net",
                           "курсовая разница"]),
    CanonicalLine("cf_employee_benefits", "Change in employee benefits",
                  section="Adjustments",
                  aliases=["change in employee benefits", "employee benefits"]),
    CanonicalLine("cf_other_adjustments", "Other adjustments",
                  section="Adjustments",
                  aliases=["other adjustments", "прочие корректировки", "прочее", "other",
                           "impairment of tr and advances paid",
                           "write-down of raw materials to nrv",
                           "gain from disposal of subsidiary",
                           "loss from disposal of subsidiary"]),
    CanonicalLine("cf_op_before_wc", "Operating cash flows before working capital changes",
                  section="Adjustments", is_subtotal=True,
                  aliases=["operating cash flows before working capital changes",
                           "operating cf before wc",
                           "cash generated from operations"]),
    CanonicalLine("cf_chg_inventories", "Changes in inventories",
                  section="Adjustments",
                  aliases=["changes in inventories", "change in inventories",
                           "запасы", "изменение запасов"]),
    CanonicalLine("cf_chg_advances", "Changes in advances paid",
                  section="Adjustments",
                  aliases=["changes in advances paid",
                           "changes in advances received",
                           "изменение авансов"]),
    CanonicalLine("cf_chg_trade_recv", "Changes in trade and other receivables",
                  section="Adjustments",
                  aliases=["changes in trade and other receivables",
                           "change in trade receivables",
                           "changes in tr",
                           "изменения в торговой и прочей дебиторской задолженности",
                           "изменение дебиторской задолженности"]),
    CanonicalLine("cf_chg_tax_recv", "Changes in other tax receivables",
                  section="Adjustments",
                  aliases=["changes in other tax receivables", "changes in tax receivables",
                           "changes in prepaid taxes other income tax"]),
    CanonicalLine("cf_chg_trade_pay", "Changes in trade and other payables",
                  section="Adjustments",
                  aliases=["changes in trade and other payables",
                           "change in trade payables",
                           "changes in tp",
                           "изменения в торговой и прочей кредиторской задолженности",
                           "изменение кредиторской задолженности"]),
    CanonicalLine("cf_chg_tax_pay", "Changes in other taxes payable",
                  section="Adjustments",
                  aliases=["changes in other taxes payable",
                           "changes in other taxes payables"]),
    CanonicalLine("cf_chg_other_liabs", "Changes in other liabilities",
                  section="Adjustments",
                  aliases=["changes in other liabilities", "change in other liabilities",
                           "changes in other current assets",
                           "changes in provisions",
                           "changes in other financial liabilities"]),
    CanonicalLine("cf_chg_wc", "Changes in working capital",
                  section="Adjustments", is_subtotal=True,
                  aliases=["changes in working capital", "change in working capital",
                           "изменение оборотного капитала"]),
    CanonicalLine("cf_income_tax_paid", "Income taxes paid",
                  section="Adjustments",
                  aliases=["income taxes paid", "income tax paid",
                           "corporate tax paid",
                           "выплаченный налог на прибыль",
                           "налог на прибыль уплаченный",
                           "уплаченный налог на прибыль"]),
    CanonicalLine("operating_cf", "Operating Cash Flow",
                  is_subtotal=True,
                  aliases=["operating cash flow", "cash flow from operating activities",
                           "operating cf", "operations cash flow",
                           "чистая сумма денежных средств от операционной деятельности",
                           "денежный поток от операционной деятельности"]),

    CanonicalLine("cf_capex", "Purchases of property, plant and equipment",
                  section="Investing activities",
                  section_alt=["Investing activities:"],
                  aliases=["purchases of property, plant and equipment", "capex",
                           "purchases of ppe",
                           "ppe additions",
                           "acquisition of other non-current assets",
                           "acquisition of subsidiary, net of cash acquired",
                           "приобретение основных средств",
                           "приобретение нематериальных активов",
                           "приобретение и продажа нематериальных активов",
                           "приобретения за вычетом поступлений от продаж основных средств",
                           "капитал қўйилмалар"]),
    CanonicalLine("cf_proceeds_ppe", "Proceeds from disposal of PPE",
                  section="Investing activities",
                  aliases=["proceeds from disposal of ppe",
                           "поступления от продажи основных средств"]),
    CanonicalLine("cf_chg_restricted_cash", "Change in restricted cash",
                  section="Investing activities",
                  aliases=["change in restricted cash",
                           "bank deposits placed", "bank deposits withdrawn"]),
    CanonicalLine("cf_other_investing", "Other investing activities",
                  section="Investing activities",
                  aliases=["dividends received", "financing of investment projects",
                           "other investing activities"]),
    CanonicalLine("investing_cf", "Investing Cash Flow",
                  is_subtotal=True,
                  aliases=["investing cash flow", "cash flow from investing activities",
                           "investment cash flow",
                           "чистая сумма денежных средств, использованных в инвестиционной деятельности"]),

    CanonicalLine("cf_dividends_paid", "Dividends paid",
                  section="Financing activities",
                  section_alt=["Financing activities:"],
                  aliases=["dividends paid", "выплаченные дивиденды", "тўланган дивидендлар",
                           "дивиденды выплаченные"]),
    CanonicalLine("cf_dividends_declared", "Dividends declared",
                  section="Financing activities",
                  aliases=["dividends declared", "deemed dividends", "объявленные дивиденды"]),
    CanonicalLine("cf_charity", "Cash paid as charity and sponsorship",
                  section="Financing activities",
                  aliases=["cash paid as charity and sponsorship",
                           "cash paid as charity and sponsorship in accordance with the orders of state regulatory and supervisory authorities",
                           "благотворительность и спонсорство"]),
    CanonicalLine("cf_proceeds_borrowings", "Proceeds from borrowings",
                  section="Financing activities",
                  aliases=["proceeds from borrowings",
                           "proceeds from bank loans",
                           "получение займов",
                           "привлечение заемных средств",
                           "заимствования полученные"]),
    CanonicalLine("cf_repayment_borrowings", "Repayment of borrowings",
                  section="Financing activities",
                  aliases=["repayment of borrowings",
                           "repayment of bank loans",
                           "погашение займов",
                           "погашение кредитов и займов",
                           "денежные выплаты и выплаты по долгосрочным и краткосрочным кредитам и займам"]),
    CanonicalLine("cf_interest_paid", "Interest paid",
                  section="Financing activities",
                  aliases=["interest paid",
                           "уплаченные проценты",
                           "проценты уплаченные",
                           "выплаченные проценты"]),
    CanonicalLine("cf_commission_borrowings", "Commission on borrowings paid",
                  section="Financing activities",
                  aliases=["commission on borrowings paid"]),
    CanonicalLine("cf_other_financing", "Other financing activities",
                  section="Financing activities",
                  aliases=["other financing activities",
                           "tax paid on shares issue",
                           "cash received from shareholder",
                           "денежные поступления от выпуска акций",
                           "другие денежные поступления и выплатьот финансовой детдельности",
                           "денежные поступления и платежи по финансовой аренде"]),
    CanonicalLine("financing_cf", "Financing Cash Flow",
                  is_subtotal=True,
                  aliases=["financing cash flow", "cash flow from financing activities",
                           "чистая сумма денежных средста, использованных в финансовой деятельности"]),

    CanonicalLine("cf_net_change", "Net increase / (decrease) in cash and cash equivalents",
                  is_subtotal=True,
                  aliases=["net increase decrease in cce", "net increase in cash",
                           "net decrease in cash",
                           "net change in cash and cash equivalents",
                           "чистое увеличение уменьшение в денежных средствах и их эквивалентах",
                           "чистое изменение денежных средств"]),
    CanonicalLine("cf_cce_open", "Cash and cash equivalents at the beginning of the year",
                  is_subtotal=True,
                  aliases=["cce at the beginning of the year",
                           "cash and cash equivalents at the beginning of the year",
                           "денежные средства на начало года",
                           "денежные средства и их эквиваленты на начало года"]),
    CanonicalLine("cf_fx_effect", "Effect of exchange rate changes on cash",
                  aliases=["effect of exchange rate changes on cce",
                           "effect of exchange rate changes on cash",
                           "effect of exchange rate changes on cash and cash equivalents",
                           "влияние изменений обменного курса валют на денежные средствя и их эквиваленты"]),
    CanonicalLine("cf_cce_close", "Cash and cash equivalents at the end of the year",
                  is_subtotal=True,
                  aliases=["cash and cash equivalents at the end of the year",
                           "cce at the end of the year",
                           "денежные средства на конец года",
                           "денежные средства и их эквиваленты на конец года",
                           "денежные средства и их эквиваленты на конец пода"]),
]


CANONICAL: dict[str, list[CanonicalLine]] = {
    "BS": BS_CANONICAL,
    "PL": PL_CANONICAL,
    "CF": CF_CANONICAL,
}


# ── Matching ────────────────────────────────────────────────────────────


# Pre-compute alias → canonical map for fast lookup. Tuple key (report_type, alias_slug).
def _build_alias_index() -> dict[tuple[str, str], list[CanonicalLine]]:
    idx: dict[tuple[str, str], list[CanonicalLine]] = {}
    for rtyp, lines in CANONICAL.items():
        for cl in lines:
            keys = [cl.label] + (cl.aliases or [])
            if cl.label_ru:
                keys.append(cl.label_ru)
            for k in keys:
                slug = _slug(k)
                if not slug:
                    continue
                idx.setdefault((rtyp, slug), []).append(cl)
    return idx


_ALIAS_INDEX = _build_alias_index()


def match_canonical(
    report_type: str,
    label: str,
    section: Optional[str] = None,
) -> Optional[CanonicalLine]:
    """Try to map a parsed row's label to a canonical line.

    Strategy:
      1. Exact slug match against alias index, filtered by section.
      2. Exact slug match without section filter (returns first match —
         disambiguation by section was already attempted in step 1).
      3. None.

    Section filter is important for duplicate labels: "Inventories" exists
    in both Non-current and Current assets — the section header determines
    which canonical row applies. Borrowings has the same issue (NC vs CUR).
    """
    if report_type not in CANONICAL:
        return None
    slug = _slug(label)
    if not slug:
        return None

    candidates = _ALIAS_INDEX.get((report_type, slug)) or []
    if not candidates:
        return None

    # Step 1: filter by section
    if section:
        for cl in candidates:
            if _section_match(section, cl.section, cl.section_alt):
                return cl
    # Step 2: if only one candidate, return it
    if len(candidates) == 1:
        return candidates[0]
    # Step 3: ambiguous — pick the one without a section requirement
    for cl in candidates:
        if not cl.section:
            return cl
    return candidates[0]


def canonical_codes(report_type: str) -> list[str]:
    """List of canonical codes for a report type, in display order."""
    return [cl.code for cl in CANONICAL.get(report_type, [])]


def canonical_dict(report_type: str) -> dict[str, CanonicalLine]:
    """Map canonical_code → CanonicalLine for a report type."""
    return {cl.code: cl for cl in CANONICAL.get(report_type, [])}
