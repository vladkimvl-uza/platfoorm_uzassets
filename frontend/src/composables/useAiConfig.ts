// frontend/src/composables/useAiConfig.ts
//
// ROLES expanded from 5 to 13 with grouping.
// Groups: Базовые / Финансы / Big4

import { ref, computed } from "vue";
import { getConfig as apiGetConfig, saveConfig as apiSaveConfig, type AiConfig } from "@/api/aiClient";

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

const ROLES: RoleOption[] = [
  // Базовые
  { group: "basic", value: "universal", label: "Универсальный",
    desc: "Общий ассистент по всем разделам" },
  { group: "basic", value: "analyst", label: "Аналитик",
    desc: "Цифры, паттерны, аномалии" },
  { group: "basic", value: "expert", label: "Эксперт",
    desc: "Стратегические рекомендации" },
  { group: "basic", value: "assistant", label: "Помощник",
    desc: "Резюме, ответы на вопросы" },
  { group: "basic", value: "financial", label: "Финансист",
    desc: "МСФО, P&L, маржинальность, ROE" },

  // Финансы
  { group: "finance", value: "investor", label: "Инвестор",
    desc: "ROIC, EV/EBITDA, FCF, exit strategy, value drivers" },

  // Big4
  { group: "big4", value: "audit_big4", label: "Big4 — Аудит",
    desc: "ISA, IFRS, ICFR, RoMM, материальность, КАМ" },
  { group: "big4", value: "tax_big4", label: "Big4 — Налоги",
    desc: "ETR, transfer pricing, СЭЗ, Налоговый кодекс РУз" },
  { group: "big4", value: "strategy_big4", label: "Big4 — Стратегия",
    desc: "MECE, Porter 5F, BCG, value chain, M&A targets" },
  { group: "big4", value: "risk_big4", label: "Big4 — Риски",
    desc: "COSO ERM, ISO 31000, KRI, heat map" },
  { group: "big4", value: "esg_big4", label: "Big4 — ESG",
    desc: "GRI/SASB/TCFD/ISSB, double materiality, Scope 1/2/3" },
  { group: "big4", value: "ma_big4", label: "Big4 — M&A",
    desc: "DCF, comparables, LBO, QoE, synergies, PMI" },
  { group: "big4", value: "forensic_big4", label: "Big4 — Форензик",
    desc: "Fraud investigation, ACFE, AML/KYC, OSINT" },
];

const GROUP_LABELS: Record<string, string> = {
  basic: "Базовые",
  finance: "Финансы",
  big4: "Big4 — специализации",
};

const STYLES = [
  { value: "structured", label: "Структурированный", desc: "Списки + вывод сначала" },
  { value: "laconic", label: "Лаконичный", desc: "2-4 предложения, главное" },
  { value: "detailed", label: "Развёрнутый", desc: "Подробные абзацы" },
  { value: "adaptive", label: "Адаптивный", desc: "Под вопрос" },
];

// model picker
export interface ModelOption {
  value: string;
  label: string;
  desc: string;
  badge?: string;
}
const MODELS: ModelOption[] = [
  { value: "ai-balanced", label: "Сбалансированный",
    desc: "Оптимальный баланс — скорость + цена + качество",
    badge: "по умолчанию" },
  { value: "ai-deep",     label: "Глубокий",
    desc: "Премиум — стратегические запросы, сложные what-if, M&A",
    badge: "x5 дороже · x2 медленнее" },
  { value: "ai-fast",     label: "Быстрый",
    desc: "Ультра-быстрый — короткие ответы, простые поиски",
    badge: "молниеносно" },
];

export function useAiConfig() {
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
    for (const r of ROLES) {
      out[r.group].push(r);
    }
    return out;
  });

  return {
    state: computed(() => _state.value),
    loading: computed(() => _loading.value),
    saving: computed(() => _saving.value),
    error: computed(() => _error.value),
    ROLES,
    STYLES,
    MODELS,
    rolesByGroup,
    GROUP_LABELS,
    load,
    save,
  };
}
