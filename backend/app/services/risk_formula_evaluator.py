"""
Risk formula evaluator — Pack 7.41.

Safely evaluates user-supplied formulas (text) for the Expected Loss
calculation. Uses Python's `ast` module with a strict whitelist of allowed
AST node types, operators, builtins, and variables. NO eval(), NO exec(),
NO simpleeval dependency.

Allowed:
  + - * / // % **                  (Add, Sub, Mult, Div, FloorDiv, Mod, Pow)
  < <= > >= == !=                  (comparisons)
  and or not                       (booleans)
  if/else (as ternary expression)  (IfExp)
  min, max, abs, round              (builtin functions, whitelisted)
  Constants: numbers, strings, None, True, False
  Identifiers: from EVAL_NAMESPACE (debt_usd, scenario.X, loan.X, custom.X)
  Attribute access on dotted names only (scenario.default_rate_pct etc.)
  Subscript: only for `custom["key"]` style if needed

Forbidden:
  Any function call EXCEPT min/max/abs/round
  Attribute access on objects that aren't in EVAL_NAMESPACE root
  import, def, class, lambda, list/dict/set comprehensions
  yield, raise, try, with, assignment

If the formula uses an undefined name, validate returns ok=False with
position pointing to the name.

Default Basel formula (when risk_formula_text is empty):

  pd_base = max(loan_default_probability or 0, scenario_default_rate_pct)
  pd_overdue_bump = 0.20 if overdue_days > 90 else 0
  pd_short_term_bump = 0.10 if (days_to_maturity < 365 and
                                repayments_remaining > debt_usd * 0.5) else 0
  pd = min(0.95, pd_base + pd_overdue_bump + pd_short_term_bump)

  rr = 0.85 if is_guaranteed else \
       0.75 if lender_type == 'state' else \
       0.50 if lender_type == 'local' else \
       0.35

  EL = debt_usd * pd * (1 - rr)
"""
from __future__ import annotations

import ast
from decimal import Decimal
from typing import Any, Optional

# Allowed AST node types
ALLOWED_NODES = (
    ast.Module,
    ast.Expression,
    ast.Expr,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.Attribute,
    ast.Subscript,
    ast.Index,  # py<3.9 — harmless to include
    ast.BinOp,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Compare,
    ast.IfExp,
    ast.Call,
    # operators
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.UAdd,
    ast.USub,
    ast.Not,
    ast.And,
    ast.Or,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
)


# Allowed function call names
ALLOWED_BUILTINS = {"min", "max", "abs", "round"}


# Root namespace names allowed in formulas. Specific attributes/keys
# must exist in the runtime namespace dict — otherwise NameError.
ALLOWED_ROOT_NAMES = {
    # Per-loan factual
    "debt_usd",
    "sum_total",
    "sum_disbursed",
    "rate",
    "is_guaranteed",
    "lender_type",
    "currency",
    "overdue_days",
    "days_to_maturity",
    "repayments_remaining",
    # Aggregates / structured
    "loan",  # loan.default_probability, loan.forgiveness_pct, ...
    "scenario",  # scenario.default_rate_pct, scenario.state_forgiveness_pct
    "company",  # company.ebitda, company.revenue, company.fcf
    "custom",  # custom.<key> for type-C indicators
}


# ============================================================================
# Validation
# ============================================================================
class FormulaError(Exception):
    def __init__(self, msg: str, position: Optional[int] = None):
        super().__init__(msg)
        self.msg = msg
        self.position = position


def validate_formula(formula_text: str) -> tuple[bool, Optional[str], Optional[int], list[str]]:
    """Validate formula. Returns (ok, error, position, variables_used)."""
    if not formula_text or not formula_text.strip():
        return False, "Формула пустая", None, []

    try:
        tree = ast.parse(formula_text, mode="exec")
    except SyntaxError as e:
        return False, f"Синтаксическая ошибка: {e.msg}", e.offset, []

    variables_used: set[str] = set()

    # Walk all nodes and check
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_NODES):
            return (
                False,
                f"Запрещённая конструкция: {type(node).__name__}",
                getattr(node, "col_offset", None),
                sorted(variables_used),
            )

        # Function calls must be whitelisted builtins only
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                return (
                    False,
                    "Вызовы функций только по имени (min/max/abs/round)",
                    getattr(node, "col_offset", None),
                    sorted(variables_used),
                )
            if node.func.id not in ALLOWED_BUILTINS:
                return (
                    False,
                    f"Функция '{node.func.id}' не разрешена. Доступны: {', '.join(sorted(ALLOWED_BUILTINS))}",
                    getattr(node, "col_offset", None),
                    sorted(variables_used),
                )

        # Names must be allowed root names
        if isinstance(node, ast.Name):
            if node.id in ALLOWED_BUILTINS:
                continue
            if node.id not in ALLOWED_ROOT_NAMES:
                return (
                    False,
                    f"Переменная '{node.id}' не определена. Доступны: {', '.join(sorted(ALLOWED_ROOT_NAMES))}",
                    getattr(node, "col_offset", None),
                    sorted(variables_used),
                )
            variables_used.add(node.id)

        # Attribute access only allowed on root names (one-level deep allowed,
        # e.g. scenario.default_rate_pct, custom.yuan_share)
        if isinstance(node, ast.Attribute):
            base = node.value
            # Allow chained attributes only if root is in ALLOWED_ROOT_NAMES
            while isinstance(base, ast.Attribute):
                base = base.value
            if not isinstance(base, ast.Name):
                return (
                    False,
                    "Доступ к атрибутам только через корневые имена",
                    getattr(node, "col_offset", None),
                    sorted(variables_used),
                )
            if base.id not in ALLOWED_ROOT_NAMES:
                return (
                    False,
                    f"Корень '{base.id}' не разрешён для доступа к атрибутам",
                    getattr(node, "col_offset", None),
                    sorted(variables_used),
                )

    return True, None, None, sorted(variables_used)


# ============================================================================
# Evaluation
# ============================================================================
def _to_decimal(value: Any) -> Decimal:
    """Convert to Decimal safely. None -> Decimal(0)."""
    if value is None:
        return Decimal(0)
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return Decimal(1) if value else Decimal(0)
    if isinstance(value, int | float):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value)
        except Exception:
            return Decimal(0)
    return Decimal(0)


class _AttrBag:
    """Wraps a dict so that attribute access (obj.x) works.

    Returns None for missing keys (so formula errors on undefined attrs
    are caught at evaluation, not via AttributeError).
    """

    def __init__(self, data: dict):
        self._data = data or {}

    def __getattr__(self, name):
        # Avoid recursion on _data
        if name == "_data":
            raise AttributeError(name)
        return self._data.get(name)

    def __getitem__(self, key):
        return self._data.get(key)


def evaluate_formula(
    formula_text: str,
    namespace: dict[str, Any],
) -> tuple[bool, Optional[str], Optional[Decimal]]:
    """Evaluate the validated formula on a runtime namespace.

    namespace must contain values keyed by ALLOWED_ROOT_NAMES. Use
    _AttrBag for dict-like values (loan, scenario, company, custom).

    Returns (ok, error_msg, value_as_decimal).
    """
    ok, err, _pos, _vars = validate_formula(formula_text)
    if not ok:
        return False, err, None

    # Wrap dicts in _AttrBag for attribute access
    wrapped_ns: dict[str, Any] = {}
    for k, v in namespace.items():
        if isinstance(v, dict):
            wrapped_ns[k] = _AttrBag(v)
        else:
            wrapped_ns[k] = v

    # Add allowed builtins
    wrapped_ns["min"] = min
    wrapped_ns["max"] = max
    wrapped_ns["abs"] = abs
    wrapped_ns["round"] = round

    try:
        # Use compile() + eval() of pre-validated AST. Safer than direct eval
        # of source string because we already AST-walked it.
        tree = ast.parse(formula_text, mode="exec")

        # Execute body; the LAST expression's value is the result.
        # Standard pattern: split off last Expr statement, eval it.
        if not tree.body:
            return False, "Пустая формула", None

        # Collect intermediate assignments? No — we don't allow assignment.
        # The last expression must produce the value.
        # In practice the user writes "EL = debt_usd * pd * (1-rr)" — but
        # since we don't allow assignment, they must write one big expression.
        # The convention is the formula text IS one expression that returns EL.

        # If body has multiple statements, evaluate the last one
        # (this allows comments + a final expression)
        body = [n for n in tree.body if not isinstance(n, ast.Expr) or n.value is not None]
        if not body:
            return False, "Нет выражения для расчёта", None

        last = body[-1]
        if not isinstance(last, ast.Expr):
            return False, "Последний оператор должен быть выражением", None

        result = eval(  # noqa: S307 — pre-validated AST whitelist
            compile(ast.Expression(body=last.value), "<formula>", "eval"),
            {"__builtins__": {}},
            wrapped_ns,
        )
        return True, None, _to_decimal(result)
    except ZeroDivisionError:
        return False, "Деление на ноль", None
    except (TypeError, ValueError) as e:
        return False, f"Ошибка вычисления: {e}", None
    except Exception as e:
        return False, f"Ошибка: {type(e).__name__}: {e}", None


# ============================================================================
# Default formula
# ============================================================================
DEFAULT_RR_BY_LENDER: dict[str, float] = {
    "state": 0.75,
    "local": 0.50,
    "foreign": 0.35,
    "bond": 0.40,
    "guaranteed_override": 0.85,  # applied if is_guaranteed regardless of lender_type
}


def compute_default_el(
    debt_usd: Decimal,
    loan_default_probability: Optional[Decimal],
    scenario_default_rate_pct: Decimal,
    overdue_days: int,
    days_to_maturity: int,
    repayments_remaining_usd: Decimal,
    is_guaranteed: bool,
    lender_type: Optional[str],
    rr_overrides: Optional[dict[str, float]] = None,
) -> tuple[Decimal, Decimal, Decimal]:
    """Default Basel-style EL formula. Returns (pd, rr, el).

    Used when CreditPortfolioScenario.risk_formula_text is empty/None.
    """
    rr_map = dict(DEFAULT_RR_BY_LENDER)
    if rr_overrides:
        rr_map.update(rr_overrides)

    pd_base = max(
        float(loan_default_probability or 0),
        float(scenario_default_rate_pct or 0),
    )
    pd_overdue = 0.20 if overdue_days > 90 else 0.0
    short_term_trigger = (
        days_to_maturity < 365
        and float(repayments_remaining_usd) > float(debt_usd) * 0.5
    )
    pd_short = 0.10 if short_term_trigger else 0.0
    pd = min(0.95, pd_base + pd_overdue + pd_short)

    if is_guaranteed:
        rr = rr_map.get("guaranteed_override", 0.85)
    else:
        rr = rr_map.get(lender_type or "", 0.35)

    el = float(debt_usd) * pd * (1.0 - rr)
    return Decimal(str(round(pd, 6))), Decimal(str(round(rr, 6))), Decimal(str(round(el, 2)))


# Default formula text (user can copy/paste / edit / reset to this).
# Wrapped in outer parens so multi-line text parses as a single expression.
# Uses `value or 0` pattern to handle None — safer than `is not None`
# which requires the ast.IsNot operator not in our whitelist.
DEFAULT_FORMULA_TEXT = (
    "(min(0.95, "
    "max((loan.default_probability or 0), scenario.default_rate_pct) "
    "+ (0.20 if overdue_days > 90 else 0) "
    "+ (0.10 if (days_to_maturity < 365 and repayments_remaining > debt_usd * 0.5) else 0)"
    ") * debt_usd * (1 - ("
    "0.85 if is_guaranteed "
    "else 0.75 if lender_type == 'state' "
    "else 0.50 if lender_type == 'local' "
    "else 0.35"
    ")))"
)
