/**
 *   - cpDrillHeroHtml(opts)
 *   - cpDrillStatGridHtml(items)
 *   - cpDrillBarsHtml(items)
 *
 * Returns HTML strings ready for use as `body` in `CpDrillModal` sections,
 *
 * The companion CpDrillModal.vue applies the styles via :deep() rules so the
 * HTML output here is class-driven and doesn't require inline styles.
 *
 * Numbers wrapped in <span data-countup> are picked up by the modal's mount-time
 * countUpScan call automatically.
 */

function escHtml(s: unknown): string {
  if (s == null) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// =====================================================================
// Hero — large number + unit + label + sub
// =====================================================================

export interface CpDrillHeroOpts {
  /** Number for data-countup */
  value: number | string;
  unit?: string;
  label?: string;
  sub?: string;
  cuDecimals?: number;
}

export function cpDrillHeroHtml(opts: CpDrillHeroOpts): string {
  const num = opts.value;
  const unit = opts.unit || "";
  const lbl = opts.label || "";
  const sub = opts.sub || "";
  const cuD = opts.cuDecimals == null ? 0 : opts.cuDecimals;
  return (
    '<div class="cp-drill-hero-numwrap">' +
    `<span class="cp-drill-hero-num" data-countup="${escHtml(num)}" data-cu-d="${cuD}">${escHtml(num)}</span>` +
    (unit ? `<span class="cp-drill-hero-unit">${escHtml(unit)}</span>` : "") +
    "</div>" +
    '<div class="cp-drill-hero-meta">' +
    (lbl ? `<div class="cp-drill-hero-lbl">${escHtml(lbl)}</div>` : "") +
    (sub ? `<div class="cp-drill-hero-sub">${escHtml(sub)}</div>` : "") +
    "</div>"
  );
}

// =====================================================================
// Stat grid — small mini-cards with value + label + optional sub + onClick
// =====================================================================

export interface CpDrillStatItem {
  label: string;
  value: number | string;
  unit?: string;
  sub?: string;
  /** CSS color override for the value */
  color?: string;
  onClick?: string;
  cuDecimals?: number;
}

export function cpDrillStatGridHtml(items: CpDrillStatItem[]): string {
  return (
    '<div class="cp-drill-stat-grid">' +
    items
      .map((s) => {
        const click = s.onClick
          ? ` class="cp-drill-stat clickable" onclick="${s.onClick}"`
          : ' class="cp-drill-stat"';
        const color = s.color ? ` style="color:${s.color}"` : "";
        const cuD = s.cuDecimals == null ? 0 : s.cuDecimals;
        const valHtml =
          typeof s.value === "number"
            ? `<span data-countup="${s.value}" data-cu-d="${cuD}">${s.value}</span>`
            : escHtml(s.value);
        return (
          `<div${click}>` +
          `<div class="cp-drill-stat-l">${escHtml(s.label)}</div>` +
          `<div class="cp-drill-stat-v"${color}>${valHtml}` +
          (s.unit ? `<span class="cp-drill-stat-u">${escHtml(s.unit)}</span>` : "") +
          `</div>` +
          (s.sub ? `<div class="cp-drill-stat-s">${escHtml(s.sub)}</div>` : "") +
          "</div>"
        );
      })
      .join("") +
    "</div>"
  );
}

// =====================================================================
// Distribution bars — label / animated track / value
// =====================================================================

export interface CpDrillBarItem {
  label: string;
  value: number;
  total?: number;
  color?: string;
  onClick?: string;
  /** Override the auto-formatted value text */
  valueText?: string;
}

export function cpDrillBarsHtml(items: CpDrillBarItem[]): string {
  if (!items.length) return "";
  const maxVal = Math.max(...items.map((i) => i.value || 0)) || 1;
  return (
    '<div class="cp-drill-bars">' +
    items
      .map((it, i) => {
        const pct = ((it.value / maxVal) * 100).toFixed(2);
        const click = it.onClick ? `onclick="${it.onClick}"` : "";
        const valTxt =
          it.valueText ||
          (it.total
            ? `${((it.value / it.total) * 100).toFixed(1)}%`
            : String(it.value));
        return (
          `<div class="cp-drill-bar-row" ${click}>` +
          `<div class="cp-drill-bar-l">${escHtml(it.label)}</div>` +
          `<div class="cp-drill-bar-track">` +
          `<div class="cp-drill-bar-fill" style="--w:${pct}%;--c:${it.color || "#7F77DD"};--bd:${i * 60}ms"></div>` +
          `</div>` +
          `<div class="cp-drill-bar-v">${escHtml(valTxt)}</div>` +
          "</div>"
        );
      })
      .join("") +
    "</div>"
  );
}

// =====================================================================
// Format helpers (used inside drill bodies)
// =====================================================================

/** @deprecated Locale-blind helper. Use `useFormatters().fmtMoneyCompact(v, "UZS")` instead. */
export function fmtCompactUzs(v: number | null | undefined): string {
  if (v == null || isNaN(Number(v))) return "—";
  const n = Number(v);
  if (n === 0) return "0";
  const sign = n < 0 ? "-" : "";
  const abs = Math.abs(n);
  if (abs >= 1e12) return sign + (abs / 1e12).toFixed(2) + " трлн";
  if (abs >= 1e9) return sign + (abs / 1e9).toFixed(2) + " млрд";
  if (abs >= 1e6) return sign + (abs / 1e6).toFixed(2) + " млн";
  if (abs >= 1e3) return sign + (abs / 1e3).toFixed(1) + " тыс.";
  return sign + abs.toFixed(0);
}

/** @deprecated Locale-blind helper. Use `useFormatters().fmtMoneyCompact(v, "USD")` instead. */
export function fmtCompactUsd(v: number | null | undefined): string {
  if (v == null || isNaN(Number(v))) return "—";
  const n = Number(v);
  if (n === 0) return "$0";
  const sign = n < 0 ? "-" : "";
  const abs = Math.abs(n);
  if (abs >= 1e9) return sign + "$" + (abs / 1e9).toFixed(2) + "B";
  if (abs >= 1e6) return sign + "$" + (abs / 1e6).toFixed(1) + "M";
  if (abs >= 1e3) return sign + "$" + (abs / 1e3).toFixed(0) + "K";
  return sign + "$" + abs.toFixed(0);
}

/** @deprecated Locale-blind helper. Use `useFormatters().fmtDateNumeric(iso)` instead. */
export function fmtDateShort(iso: string | null | undefined): string {
  if (!iso) return "—";
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return iso;
  return `${m[3]}.${m[2]}.${m[1].slice(2)}`;
}
