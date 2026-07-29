// frontend/src/composables/useAiConfig.ts
//
// ROLES expanded from 5 to 13 with grouping.
// Groups: Базовые / Финансы / Big4

import { ref, computed } from "vue";
import { getConfig as apiGetConfig, saveConfig as apiSaveConfig, type AiConfig } from "@/api/aiClient";
import { t } from "@/locale/i18n";

const _state = ref<AiConfig | null>(null);
const _loading = ref(false);
const _saving = ref(false);
const _error = ref<string | null>(null);
let _loaded = false;

export interface RoleOption {
  value: string;
  label: string;
  desc: string;
  group: "basic" | "finance" | "big4";
}

// model picker
export interface ModelOption {
  value: string;
  label: string;
  desc: string;
  badge?: string;
}
export function useAiConfig() {
  const roles = computed<RoleOption[]>(() => [
    { group: "basic", value: "universal", label: t("Универсальный"), desc: t("Общий ассистент по всем разделам") },
    { group: "basic", value: "analyst", label: t("Аналитик"), desc: t("Цифры, паттерны, аномалии") },
    { group: "basic", value: "expert", label: t("Эксперт"), desc: t("Стратегические рекомендации") },
    { group: "basic", value: "assistant", label: t("Помощник"), desc: t("Резюме, ответы на вопросы") },
    { group: "basic", value: "financial", label: t("Финансист"), desc: t("МСФО, P&L, маржинальность, ROE") },
    { group: "finance", value: "investor", label: t("Инвестор"), desc: t("ROIC, EV/EBITDA, FCF, exit strategy, value drivers") },
    { group: "big4", value: "audit_big4", label: t("Big4 — Аудит"), desc: t("ISA, IFRS, ICFR, RoMM, материальность, КАМ") },
    { group: "big4", value: "tax_big4", label: t("Big4 — Налоги"), desc: t("ETR, transfer pricing, СЭЗ, Налоговый кодекс РУз") },
    { group: "big4", value: "strategy_big4", label: t("Big4 — Стратегия"), desc: t("MECE, Porter 5F, BCG, value chain, M&A targets") },
    { group: "big4", value: "risk_big4", label: t("Big4 — Риски"), desc: t("COSO ERM, ISO 31000, KRI, heat map") },
    { group: "big4", value: "esg_big4", label: t("Big4 — ESG"), desc: t("GRI/SASB/TCFD/ISSB, double materiality, Scope 1/2/3") },
    { group: "big4", value: "ma_big4", label: t("Big4 — M&A"), desc: t("DCF, comparables, LBO, QoE, synergies, PMI") },
    { group: "big4", value: "forensic_big4", label: t("Big4 — Форензик"), desc: t("Fraud investigation, ACFE, AML/KYC, OSINT") },
  ]);
  const groupLabels = computed<Record<string, string>>(() => ({
    basic: t("Базовые"),
    finance: t("Финансы"),
    big4: t("Big4 — специализации"),
  }));
  const styles = computed(() => [
    { value: "structured", label: t("Структурированный"), desc: t("Списки + вывод сначала") },
    { value: "laconic", label: t("Лаконичный"), desc: t("2-4 предложения, главное") },
    { value: "detailed", label: t("Развёрнутый"), desc: t("Подробные абзацы") },
    { value: "adaptive", label: t("Адаптивный"), desc: t("Под вопрос") },
  ]);
  const models = computed<ModelOption[]>(() => [
    { value: "ai-balanced", label: t("Сбалансированный"), desc: t("Оптимальный баланс — скорость + цена + качество"), badge: t("по умолчанию") },
    { value: "ai-deep", label: t("Глубокий"), desc: t("Премиум — стратегические запросы, сложные what-if, M&A"), badge: t("x5 дороже · x2 медленнее") },
    { value: "ai-fast", label: t("Быстрый"), desc: t("Ультра-быстрый — короткие ответы, простые поиски"), badge: t("молниеносно") },
  ]);

  async function load(force = false): Promise<AiConfig | null> {
    if (_loaded && !force && _state.value) return _state.value;
    _loading.value = true;
    _error.value = null;
    try {
      const cfg = await apiGetConfig();
      _state.value = cfg;
      _loaded = true;
      return cfg;
    } catch (e: unknown) {
      _error.value = e instanceof Error ? e.message : String(e);
      return null;
    } finally {
      _loading.value = false;
    }
  }

  async function save(patch: Partial<AiConfig>): Promise<AiConfig | null> {
    _saving.value = true;
    _error.value = null;
    try {
      const cfg = await apiSaveConfig(patch);
      _state.value = cfg;
      return cfg;
    } catch (e: unknown) {
      _error.value = e instanceof Error ? e.message : String(e);
      return null;
    } finally {
      _saving.value = false;
    }
  }

  // Roles grouped: { basic: [...], finance: [...], big4: [...] }
  const rolesByGroup = computed(() => {
    const out: Record<string, RoleOption[]> = { basic: [], finance: [], big4: [] };
    for (const r of roles.value) {
      out[r.group].push(r);
    }
    return out;
  });

  return {
    state: computed(() => _state.value),
    loading: computed(() => _loading.value),
    saving: computed(() => _saving.value),
    error: computed(() => _error.value),
    roles,
    styles,
    models,
    rolesByGroup,
    groupLabels,
    load,
    save,
  };
}
