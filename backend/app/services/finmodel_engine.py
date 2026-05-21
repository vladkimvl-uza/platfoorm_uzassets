"""FinModel v2 formula engine — Phase 1.4.

Evaluates canonical NSBU formulas using Decimal throughout (no float).
Supported syntax (1:1 с handoff):
  '010-011'           → values['010'] - values['011']
  '010+020'           → addition
  'SUM(040..080)'     → range sum (по order_idx внутри section)
  'SUM(PL_010,PL_020)'→ explicit list
  'PL_010+PL_020'     → mixed arithmetic

Order matters — топологическая сортировка по зависимостям.
"""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Dict, List, Optional, Sequence

# Compiled regexes
# Note: NSBU codes start with digit ('010', '400') OR letter ('PL_010', 'CHECK').
# Identifier pattern allows digit at start, but not '+' or '-'.
_RE_SUM_RANGE = re.compile(r"^SUM\(([A-Za-z0-9_]+)\.\.([A-Za-z0-9_]+)\)$")
_RE_SUM_LIST  = re.compile(r"^SUM\(([\w_,\s]+)\)$")
_RE_TOKEN     = re.compile(r"([+\-]?)\s*([A-Za-z0-9_]+)")
_RE_DEP_TOKEN = re.compile(r"[A-Za-z0-9_]+")
_ZERO = Decimal("0")


class TemplateRowProto:
    """Minimal duck-type for template row used by engine."""
    code: str
    section: str
    order_idx: int
    row_type: str
    formula: Optional[str]


class FormulaEngine:
    """Pure-function engine: ingest template + value dict → return complete dict."""

    def __init__(self, template_rows: Sequence[TemplateRowProto]):
        self.rows = list(template_rows)
        self.rows_by_code: Dict[str, TemplateRowProto] = {r.code: r for r in self.rows}
        # Pre-build per-section ordered code lists (for SUM(a..b) range expansion)
        self._codes_in_section: Dict[str, List[str]] = {}
        for r in sorted(self.rows, key=lambda x: (x.section, x.order_idx)):
            self._codes_in_section.setdefault(r.section, []).append(r.code)
        # Pre-compute topological order
        self._topo_order = self._build_topological_order()

    # ─── Public API ─────────────────────────────────────────────────
    def compute_all(self, values: Dict[str, Decimal]) -> Dict[str, Decimal]:
        """Take partial dict (inputs filled), return full dict including all
        subtotals + grands + checks computed in dependency order."""
        result: Dict[str, Decimal] = {k: _to_decimal(v) for k, v in values.items() if v is not None}
        for code in self._topo_order:
            row = self.rows_by_code[code]
            if row.row_type in ("subtotal", "grand", "check") and row.formula:
                try:
                    result[code] = self._eval(row.formula, result, row.section)
                except Exception:
                    # Bad formula or missing reference — set to 0 so downstream cells still compute
                    result[code] = _ZERO
        return result

    def balance_check(self, values: Dict[str, Decimal]) -> Dict[str, object]:
        """Return {is_balanced, delta, asset_total, liab_total}."""
        asset = values.get("400", _ZERO) or _ZERO
        liab = values.get("780", _ZERO) or _ZERO
        delta = liab - asset
        return {
            "is_balanced": abs(delta) < Decimal("0.01"),
            "delta": str(delta),
            "asset_total": str(asset),
            "liab_total": str(liab),
        }

    # ─── Internals ──────────────────────────────────────────────────
    def _build_topological_order(self) -> List[str]:
        """Topo-sort: codes with no formula come first; subtotals depend on inputs."""
        # Build dep graph
        deps: Dict[str, set] = {}
        for r in self.rows:
            if r.formula and r.row_type in ("subtotal", "grand", "check"):
                deps[r.code] = self._extract_deps(r.formula, r.section)
            else:
                deps[r.code] = set()

        # Kahn's algorithm
        in_degree: Dict[str, int] = {c: 0 for c in deps}
        for code, dep_set in deps.items():
            for d in dep_set:
                if d in in_degree:
                    in_degree[code] += 0  # we count edges FROM dep TO code
        # rebuild: for each code, edges go from each dep → code
        adj: Dict[str, List[str]] = {c: [] for c in deps}
        in_deg: Dict[str, int] = {c: 0 for c in deps}
        for code, dep_set in deps.items():
            for d in dep_set:
                if d in deps:
                    adj[d].append(code)
                    in_deg[code] += 1

        queue = [c for c, deg in in_deg.items() if deg == 0]
        # Stable order: sort initial queue by (section, order_idx) so same-tier
        # codes have deterministic processing
        queue.sort(key=lambda c: (self.rows_by_code[c].section, self.rows_by_code[c].order_idx))

        result: List[str] = []
        while queue:
            c = queue.pop(0)
            result.append(c)
            # process neighbours in stable order
            for nxt in sorted(adj[c], key=lambda x: (self.rows_by_code[x].section, self.rows_by_code[x].order_idx)):
                in_deg[nxt] -= 1
                if in_deg[nxt] == 0:
                    queue.append(nxt)
        # Cycles → append remaining at the end (engine still computes, just unordered)
        for c in deps:
            if c not in result:
                result.append(c)
        return result

    def _extract_deps(self, formula: str, section: str) -> set:
        """Return set of row_code identifiers referenced by formula."""
        if not formula:
            return set()
        f = formula.strip()
        m = _RE_SUM_RANGE.match(f)
        if m:
            return set(self._range_codes(m.group(1), m.group(2), section))
        m = _RE_SUM_LIST.match(f)
        if m:
            return {c.strip() for c in m.group(1).split(",") if c.strip()}
        return set(_RE_DEP_TOKEN.findall(f))

    def _eval(self, formula: str, values: Dict[str, Decimal], section: str) -> Decimal:
        f = formula.strip()
        m = _RE_SUM_RANGE.match(f)
        if m:
            codes = self._range_codes(m.group(1), m.group(2), section)
            return sum((values.get(c, _ZERO) or _ZERO for c in codes), _ZERO)
        m = _RE_SUM_LIST.match(f)
        if m:
            codes = [c.strip() for c in m.group(1).split(",") if c.strip()]
            return sum((values.get(c, _ZERO) or _ZERO for c in codes), _ZERO)
        # Simple arithmetic with +/- tokens
        total = _ZERO
        for sign, code in _RE_TOKEN.findall(f):
            v = values.get(code, _ZERO) or _ZERO
            if sign == "-":
                total -= v
            else:
                total += v
        return total

    def _range_codes(self, start: str, end: str, section: str) -> List[str]:
        """All codes in section between start and end (inclusive) by order_idx."""
        section_codes = self._codes_in_section.get(section, [])
        if start not in section_codes or end not in section_codes:
            return []
        i_start = section_codes.index(start)
        i_end = section_codes.index(end)
        if i_start > i_end:
            i_start, i_end = i_end, i_start
        return section_codes[i_start:i_end + 1]


def _to_decimal(v) -> Decimal:
    if v is None:
        return _ZERO
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v))
    except Exception:
        return _ZERO
