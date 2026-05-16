import { defineStore } from "pinia";
import { ref, watch } from "vue";

const LS_KEY = "uza_portfolio_year";

/**
 * Global "active portfolio year" — applied to tasks, projects, KPI, and other
 *
 * The selected year is persisted in localStorage so it survives page reload.
 */
export const usePortfolioYearStore = defineStore("portfolioYear", () => {
  const stored = localStorage.getItem(LS_KEY);
  const year = ref<number>(stored ? parseInt(stored, 10) : new Date().getFullYear());

  // Available years populated by API responses (e.g. /tasks, /projects)
  const availableYears = ref<number[]>([]);

  watch(year, (newVal) => {
    if (newVal && Number.isFinite(newVal)) {
      localStorage.setItem(LS_KEY, String(newVal));
    }
  });

  function setYear(y: number) {
    year.value = y;
  }

  function setAvailableYears(years: number[]) {
    if (Array.isArray(years) && years.length) {
      availableYears.value = [...years].sort((a, b) => b - a);
      // If current year is not in the list, snap to nearest
      if (!availableYears.value.includes(year.value)) {
        year.value = availableYears.value[0];
      }
    }
  }

  return { year, availableYears, setYear, setAvailableYears };
});
