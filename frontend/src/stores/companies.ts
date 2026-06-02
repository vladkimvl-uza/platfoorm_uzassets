/**
 * stores/companies.ts
 * ─────────────────────────────────────────────────────────────────
 * Pinia store for the 22 portfolio companies.
 *
 * - Fetches the full list once via companiesApi.list()
 * - Groups by sector with stable sort (sector.sort_order, then company.sort_order)
 * - Exposes findByCode(code) for active-link detection
 *
 * Used by SidebarCompaniesSection.vue and any other view that needs
 * the cached company list (avoids re-fetching 22 records on every navigation).
 */

import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { companiesApi } from "@/api/companies";
import { companyDisplayName, sectorDisplayName } from "@/utils/displayNames";
import { usePortfolioYearStore } from "@/stores/portfolioYear";

// ─── Lightweight types (resilient to backend shape variations) ───
interface CompanyLite {
  id: string;
  code: string;
  name_ru: string;
  name_short: string | null;
  sector_code: string | null;
  sector_name: string | null;
  sector_color: string | null;
  sort_order: number | null;
  is_active?: boolean;
  hidden_years?: number[] | null;
  logo_url?: string | null;
}

interface SectorLite {
  id?: string;
  code: string;
  name_ru: string;
  color_hex?: string | null;
  sort_order?: number | null;
}

// ─── Fallback palette for sectors without color_hex set ───
const SECTOR_COLOR_FALLBACK: Record<string, string> = {
  mining_metallurgy: "#7F77DD",
  oil_gas:           "#EF9F27",
  energy:            "#378ADD",
  transport_telecom: "#1D9E75",
  other:             "#888780",
};

export interface SectorGroup {
  sector: SectorLite & { color: string };
  companies: CompanyLite[];
}

export const useCompaniesStore = defineStore("companies", () => {
  // ─── State ───
  const companies = ref<CompanyLite[]>([]);
  const sectors   = ref<SectorLite[]>([]);
  const loading   = ref(false);
  const loaded    = ref(false);
  const error     = ref<string | null>(null);

  // ─── Actions ───

  /** Mark cache stale so the next ensureLoaded() refetches. Call after create/update/delete. */
  function invalidate(): void {
    loaded.value = false;
  }

  /** Force-refresh: invalidate + reload in one call. */
  async function reload(): Promise<void> {
    loaded.value = false;
    await ensureLoaded(true);
  }

  /** Fetch the company list once. Call ensureLoaded() — it's a no-op if already loaded. */
  async function ensureLoaded(force = false): Promise<void> {
    if (loaded.value && !force) return;
    if (loading.value) return;  // de-duplicate concurrent calls
    loading.value = true;
    error.value = null;
    try {
      const resp = await companiesApi.list();
      // Resilient unpacking — different backend shapes may use items/companies key
      const items: CompanyLite[] =
        (resp as any).items ||
        (resp as any).companies ||
        (Array.isArray(resp) ? resp : []);
      companies.value = items.filter(c => c && c.is_active !== false);
      sectors.value   = (resp as any).sectors || [];
      loaded.value    = true;
    } catch (e: any) {
      error.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить компании";
      console.warn("[companies store] fetch failed:", e);
    } finally {
      loading.value = false;
    }
  }

  // ─── Getters ───

  // Компании, видимые в ТЕКУЩЕМ выбранном году (исключаем скрытые per-year).
  // Реактивно зависит от portfolioYear → при смене FY список обновляется.
  const yearStore = usePortfolioYearStore();
  const visibleCompanies = computed<CompanyLite[]>(() => {
    const y = yearStore.year;
    return companies.value.filter(c => !(Array.isArray(c.hidden_years) && c.hidden_years.includes(y)));
  });

  /** Companies grouped by sector, sorted by sector.sort_order then company.sort_order. */
  const bySector = computed<SectorGroup[]>(() => {
    if (!visibleCompanies.value.length) return [];

    // Build lookup of sector metadata from the sectors[] response
    const sectorMeta = new Map<string, SectorLite>();
    sectors.value.forEach(s => sectorMeta.set(s.code, s));

    // Group companies by sector_code (each company knows its sector)
    const groups = new Map<string, SectorGroup>();
    for (const c of visibleCompanies.value) {
      const key = c.sector_code || "_none";
      if (!groups.has(key)) {
        const meta = sectorMeta.get(key);
        const color =
          (meta?.color_hex && meta.color_hex.trim()) ||
          c.sector_color ||
          SECTOR_COLOR_FALLBACK[key] ||
          "#888780";
        groups.set(key, {
          sector: {
            ...(meta || {}),
            code: key,
            name_ru: meta?.name_ru || c.sector_name || (key === "_none" ? "Без сектора" : key),
            color,
          },
          companies: [],
        });
      }
      groups.get(key)!.companies.push(c);
    }

    // Sort groups by sector.sort_order (stable fallback to insertion order)
    const result = Array.from(groups.values());
    result.sort((a, b) => {
      const oa = a.sector.sort_order ?? 9999;
      const ob = b.sector.sort_order ?? 9999;
      return oa - ob;
    });

    // Sort companies inside each group by sort_order
    result.forEach(g =>
      g.companies.sort((a, b) => (a.sort_order ?? 9999) - (b.sort_order ?? 9999))
    );

    return result;
  });

  /** Total count of active companies. */
  const totalCount = computed(() => companies.value.length);

  /** Find a company by its `code` (case-insensitive). */
  function findByCode(code: string): CompanyLite | undefined {
    if (!code) return undefined;
    const lc = code.toLowerCase();
    return companies.value.find(c => c.code?.toLowerCase() === lc);
  }

  /** Resolve sector_code for a given company code. Useful for auto-expanding the right sector. */
  function findSectorCode(code: string): string | null {
    return findByCode(code)?.sector_code || null;
  }

  // ─────────────────── Display-name helpers (Pack 7.12) ───────────────────
  // Единая точка для получения отображаемых имён.
  // Правило: name_short если есть, иначе name_ru. См. utils/displayNames.ts.

  /** Find a sector by its `code`. */
  function findSectorByCode(code: string | null | undefined): SectorLite | undefined {
    if (!code) return undefined;
    return sectors.value.find(s => s.code === code);
  }

  /** Get the canonical display name for a company by its code. Empty string if not found. */
  function getCompanyName(code: string | null | undefined): string {
    return companyDisplayName(findByCode(code || ""));
  }

  /** Get the canonical display name for a sector by its code. Empty string if not found. */
  function getSectorName(code: string | null | undefined): string {
    const sec = findSectorByCode(code);
    if (sec) return sectorDisplayName(sec);
    // Fallback: компания могла принести sector_name напрямую (если sectors[] не загружены)
    const co = companies.value.find(c => c.sector_code === code);
    if (co?.sector_name) return co.sector_name;
    return code || "";
  }

  /** Find a company object (full DTO) by its UUID id. */
  function findById(id: string | null | undefined): CompanyLite | undefined {
    if (!id) return undefined;
    return companies.value.find(c => c.id === id);
  }

  /** Get display name by company UUID. */
  function getCompanyNameById(id: string | null | undefined): string {
    return companyDisplayName(findById(id));
  }

  /** Логотип компании (data-URL/URL) по UUID — null если нет. */
  function getCompanyLogoById(id: string | null | undefined): string | null {
    return findById(id)?.logo_url || null;
  }

  /** Логотип компании по коду — null если нет. */
  function getCompanyLogoByCode(code: string | null | undefined): string | null {
    if (!code) return null;
    return findByCode(code)?.logo_url || null;
  }

  return {
    // state
    companies, sectors, loading, loaded, error,
    // getters
    bySector, totalCount,
    // actions
    ensureLoaded, invalidate, reload, findByCode, findSectorCode,
    // Pack 7.12: unified naming
    findSectorByCode, findById,
    getCompanyName, getCompanyNameById, getSectorName,
    getCompanyLogoById, getCompanyLogoByCode,
  };
});
