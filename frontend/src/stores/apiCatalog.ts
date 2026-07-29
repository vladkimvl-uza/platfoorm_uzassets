/**
 * Pinia store for the API catalog (Phase 5.2).
 * 5-minute TTL cache on `summary` — catalog changes only on backend
 * redeploy, so re-fetching every page nav is wasteful.
 */
import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { t } from "@/locale/i18n";
import {
  apiCatalog,
  type CatalogSummary,
  type CompanyCatalogResponse,
  type CatalogEndpointWithSubstitution,
} from "@/api/apiCatalog";

const FIVE_MIN_MS = 5 * 60 * 1000;

export const useApiCatalogStore = defineStore("apiCatalog", () => {
  const summary       = ref<CatalogSummary | null>(null);
  const summaryError  = ref<string | null>(null);
  const summaryFetched= ref<number | null>(null);
  const summaryLoading= ref(false);

  // Per-company catalogs cached by `${companyId}:${tab||''}` for the session
  const companyCache  = ref<Record<string, { resp: CompanyCatalogResponse; fetched: number }>>({});

  async function loadSummary(force = false): Promise<CatalogSummary | null> {
    if (!force
        && summary.value
        && summaryFetched.value
        && Date.now() - summaryFetched.value < FIVE_MIN_MS) {
      return summary.value;
    }
    summaryLoading.value = true;
    summaryError.value = null;
    try {
      summary.value = await apiCatalog.summary();
      summaryFetched.value = Date.now();
      return summary.value;
    } catch (e: any) {
      summaryError.value = e?.response?.data?.detail || e?.message || t("Не удалось загрузить каталог");
      return null;
    } finally {
      summaryLoading.value = false;
    }
  }

  async function loadByCompany(
    companyId: string,
    tab?: string,
    force = false,
  ): Promise<CompanyCatalogResponse | null> {
    const key = `${companyId}:${tab || ""}`;
    const cached = companyCache.value[key];
    if (!force && cached && Date.now() - cached.fetched < FIVE_MIN_MS) {
      return cached.resp;
    }
    try {
      const resp = await apiCatalog.byCompany(companyId, tab);
      companyCache.value[key] = { resp, fetched: Date.now() };
      return resp;
    } catch {
      return null;
    }
  }

  /** Drop all per-company caches — call after a save mutates the catalog (rare). */
  function invalidate() {
    summary.value       = null;
    summaryFetched.value= null;
    companyCache.value  = {};
  }

  const groupedSummary = computed(() => {
    if (!summary.value) return [] as Array<{ group: string; modules: typeof summary.value.modules }>;
    const groups: Record<string, typeof summary.value.modules> = {};
    for (const m of summary.value.modules) {
      const g = m.group || t("Прочее");
      (groups[g] ||= []).push(m);
    }
    return Object.entries(groups).map(([group, modules]) => ({ group, modules }));
  });

  return {
    summary, summaryError, summaryFetched, summaryLoading,
    companyCache,
    groupedSummary,
    loadSummary, loadByCompany, invalidate,
  };
});

/** Filter helper — group endpoints by HTTP method into ordered buckets. */
export function groupEndpointsByMethod(endpoints: CatalogEndpointWithSubstitution[]) {
  const order: HttpMethodOrder[] = ["GET", "PATCH", "POST", "PUT", "DELETE", "WEBSOCKET"];
  const map = new Map<HttpMethodOrder, CatalogEndpointWithSubstitution[]>();
  for (const m of order) map.set(m, []);
  for (const e of endpoints) {
    const key = (order.includes(e.method as HttpMethodOrder) ? e.method : "GET") as HttpMethodOrder;
    map.get(key)!.push(e);
  }
  return Array.from(map.entries())
    .filter(([, list]) => list.length > 0)
    .map(([method, list]) => ({ method, list }));
}
type HttpMethodOrder = "GET" | "PATCH" | "POST" | "PUT" | "DELETE" | "WEBSOCKET";
