/**
 * Parse user-entered decimal string with locale tolerance:
 *   "1 234,56" → 1234.56
 *   "1234.56"  → 1234.56
 *   ""         → null
 *   "abc"      → null
 *
 * Centralized helper (was duplicated in SystemConfig.vue + ScenariosTab.vue).
 */
export function parseDecimal(s: string | null | undefined): number | null {
  if (s == null) return null;
  const t = String(s).trim();
  if (t === "") return null;
  const cleaned = t.replace(/\s+/g, "").replace(",", ".");
  const n = Number(cleaned);
  return isFinite(n) ? n : null;
}
