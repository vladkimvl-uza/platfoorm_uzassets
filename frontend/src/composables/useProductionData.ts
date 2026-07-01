import { ref, shallowRef } from "vue";
import { productionApi, type ProdOverview } from "@/api/production";

/** State for the Production-indicators tab (mirrors useBusinessPlanData shape). */
export function useProductionData() {
  const year = ref<number>(new Date().getFullYear());
  const period = ref<string>("h1");
  const data = shallowRef<ProdOverview | null>(null);
  const loading = ref(false);
  const error = ref<string | null>(null);
  const availableYears = ref<number[]>([new Date().getFullYear()]);
  let seq = 0;

  async function load() {
    loading.value = true;
    error.value = null;
    const my = ++seq;
    try {
      const d = await productionApi.overview(year.value, period.value);
      if (my !== seq) return;
      data.value = d;
    } catch (e: unknown) {
      if (my !== seq) return;
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      error.value = err?.response?.data?.detail || err?.message || "Ошибка загрузки";
      data.value = null;
    } finally {
      if (my === seq) loading.value = false;
    }
  }

  async function loadAvailable() {
    try {
      const a = await productionApi.available();
      if (a?.years?.length) {
        availableYears.value = a.years;
        if (!a.years.includes(year.value)) year.value = a.years[0];
      }
    } catch { /* ignore */ }
  }

  function setYear(y: number) { year.value = y; load(); }
  function setPeriod(p: string) { period.value = p; load(); }

  return { year, period, data, loading, error, availableYears, load, loadAvailable, setYear, setPeriod };
}
