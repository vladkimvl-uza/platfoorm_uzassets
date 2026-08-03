import { unitCostCatalogKeys } from "@/locale/dict/unit_cost_catalog";
import { t } from "@/locale/i18n";

/** Translate only canonical Unit Cost catalog values; keep manual DB text verbatim. */
export function unitCostCatalogText(value: string | null | undefined): string {
  if (!value) return "";
  const key = value.trim();
  return unitCostCatalogKeys.has(key) ? t(key) : value;
}
