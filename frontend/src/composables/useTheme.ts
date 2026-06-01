// D12 — управление темой. Ставит data-theme на <html>, персистит в localStorage.
import { ref } from "vue";

const KEY = "uza-theme";
export type ThemeMode = "light" | "dark";

export const currentTheme = ref<ThemeMode>("light");

export function applyTheme(t: ThemeMode): void {
  currentTheme.value = t;
  document.documentElement.setAttribute("data-theme", t);
  try { localStorage.setItem(KEY, t); } catch { /* ignore */ }
}

export function initTheme(): void {
  let t: ThemeMode = "light";
  try { if (localStorage.getItem(KEY) === "dark") t = "dark"; } catch { /* ignore */ }
  applyTheme(t);
}

export function toggleTheme(): void {
  applyTheme(currentTheme.value === "dark" ? "light" : "dark");
}
