/**
 * useBusinessPlanData — central state for BP module.
 * View modes: 'summary' (portfolio-wide) | 'company' (single company).
 */
import { computed, ref, shallowRef } from "vue";
import {
  bpApi,
  type AvailableCompany,
  type BpAttentionIssue,
  type BpCell,
  type BpComment,
  type BpComputed,
  type BpPeriod,
  type BpSummary,
} from "@/api/bpKpi";

export type BpViewMode = "summary" | "company";

const viewMode = ref<BpViewMode>("summary");
const selectedCompanyId = ref<string | null>(null);
const selectedYear = ref<number>(new Date().getFullYear());
const selectedPeriod = ref<BpPeriod>("annual");

const companies = shallowRef<AvailableCompany[]>([]);
const summary = shallowRef<BpSummary | null>(null);
const computed_ = shallowRef<BpComputed | null>(null);
const attention = shallowRef<BpAttentionIssue[]>([]);
const comment = shallowRef<BpComment | null>(null);
const rawRecords = shallowRef<Record<string, Record<string, BpCell>> | null>(null);

const isLoading = ref(false);
const isLoadingSummary = ref(false);
const isLoadingCompany = ref(false);
const error = ref<string | null>(null);

export function useBusinessPlanData() {
  function _logErr(scope: string, e: unknown) {
    const err = e as {
      response?: { status?: number; data?: { detail?: string } };
      message?: string;
    };
    const msg =
      err?.response?.data?.detail ||
      err?.message ||
      "Ошибка загрузки";
    error.value = msg;
    console.error(`[BP] ${scope} failed:`, msg, err?.response?.data);
  }

  async function loadCompanies() {
    if (isLoading.value) return;
    isLoading.value = true;
    try {
      companies.value = await bpApi.availableCompanies();
      // Auto-select first company if none selected
      if (!selectedCompanyId.value && companies.value.length) {
        selectedCompanyId.value = companies.value[0].company_id;
      }
      // Auto-pick year from selected co's available years
      if (selectedCompanyId.value) {
        const co = companies.value.find((c) => c.company_id === selectedCompanyId.value);
        if (co && co.years.length && !co.years.includes(selectedYear.value)) {
          selectedYear.value = co.years[0];
        }
      }
    } catch (e) {
      _logErr("companies", e);
    } finally {
      isLoading.value = false;
    }
  }

  async function loadSummary(headlineMetric: string = "revenue") {
    if (isLoadingSummary.value) return;
    isLoadingSummary.value = true;
    error.value = null;
    try {
      summary.value = await bpApi.getSummary(
        selectedYear.value, selectedPeriod.value, headlineMetric,
      );
    } catch (e) {
      _logErr("summary", e);
    } finally {
      isLoadingSummary.value = false;
    }
  }

  async function loadCompanyData() {
    if (!selectedCompanyId.value) {
      computed_.value = null;
      return;
    }
    if (isLoadingCompany.value) return;
    isLoadingCompany.value = true;
    error.value = null;
    try {
      const cid = selectedCompanyId.value;
      const yr = selectedYear.value;
      const p = selectedPeriod.value;
      const [c, a, cm] = await Promise.all([
        bpApi.getComputed(cid, yr, p),
        bpApi.getAttention(cid, yr, p),
        bpApi.getComment(cid, yr, p),
      ]);
      computed_.value = c;
      attention.value = a;
      comment.value = cm;
    } catch (e) {
      _logErr("company data", e);
    } finally {
      isLoadingCompany.value = false;
    }
  }

  async function loadRaw() {
    if (!selectedCompanyId.value) {
      rawRecords.value = null;
      return;
    }
    try {
      rawRecords.value = await bpApi.getRaw(selectedCompanyId.value, selectedYear.value);
    } catch (e) {
      _logErr("raw", e);
    }
  }

  async function setViewMode(mode: BpViewMode) {
    viewMode.value = mode;
    if (mode === "summary") await loadSummary();
    else await loadCompanyData();
  }

  async function setCompany(id: string | null) {
    selectedCompanyId.value = id;
    // Adjust year if needed
    if (id) {
      const co = companies.value.find((c) => c.company_id === id);
      if (co && co.years.length && !co.years.includes(selectedYear.value)) {
        selectedYear.value = co.years[0];
      }
    }
    if (viewMode.value === "company") await loadCompanyData();
  }

  async function setYear(y: number) {
    selectedYear.value = y;
    if (viewMode.value === "summary") await loadSummary();
    else await loadCompanyData();
  }

  async function setPeriod(p: BpPeriod) {
    selectedPeriod.value = p;
    if (viewMode.value === "summary") await loadSummary();
    else await loadCompanyData();
  }

  const availableYears = computed<number[]>(() => {
    const years = new Set<number>();
    companies.value.forEach((c) => c.years.forEach((y) => years.add(y)));
    const cur = new Date().getFullYear();
    [cur - 1, cur, cur + 1].forEach((y) => years.add(y));
    return Array.from(years).sort((a, b) => b - a).slice(0, 6);
  });

  const selectedCompany = computed<AvailableCompany | null>(() =>
    selectedCompanyId.value
      ? companies.value.find((c) => c.company_id === selectedCompanyId.value) || null
      : null,
  );

  return {
    // state
    viewMode,
    selectedCompanyId,
    selectedYear,
    selectedPeriod,
    companies,
    summary,
    computed: computed_,
    attention,
    comment,
    rawRecords,
    isLoading,
    isLoadingSummary,
    isLoadingCompany,
    error,
    // computed
    availableYears,
    selectedCompany,
    // actions
    loadCompanies,
    loadSummary,
    loadCompanyData,
    loadRaw,
    setViewMode,
    setCompany,
    setYear,
    setPeriod,
  };
}
