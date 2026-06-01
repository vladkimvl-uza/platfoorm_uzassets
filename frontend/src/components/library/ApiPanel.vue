<script setup lang="ts">
/**
 * Right-side API panel (Phase 5.3). Shows endpoints contextual to the
 * currently-open Detail tab, with company UUID substituted into paths.
 *
 * Toggleable — pref saved to localStorage. Auto-loads when tab changes.
 */
import { computed, ref, watch } from "vue";
import { useApiCatalogStore } from "@/stores/apiCatalog";
import type { CatalogEndpointWithSubstitution } from "@/api/apiCatalog";
import EndpointCard from "./EndpointCard.vue";

const props = defineProps<{
  companyId: string;
  currentTab: string;
}>();

const emit = defineEmits<{
  (e: "open-try", endpoint: CatalogEndpointWithSubstitution): void;
}>();

const store = useApiCatalogStore();

const endpoints = ref<CatalogEndpointWithSubstitution[]>([]);
const loading   = ref(false);
const error     = ref<string | null>(null);

async function refresh() {
  loading.value = true;
  error.value = null;
  try {
    const resp = await store.loadByCompany(props.companyId, props.currentTab);
    endpoints.value = resp ? resp.endpoints : [];
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить endpoints";
    endpoints.value = [];
  } finally {
    loading.value = false;
  }
}

watch(() => [props.companyId, props.currentTab], refresh, { immediate: true });

const tabLabel = computed<string>(() => {
  return ({
    overview:   "Обзор",
    financials: "Финансы",
    kpi:        "KPI · BP",
    ratings:    "Рейтинги",
    loans:      "Кредит",
    procurement:"Закупки",
    documents:  "Документы",
    identity:   "Идентификация",
    governance: "Корп. упр.",
    esg:        "ESG",
    consultants:"Консультанты",
    notes:      "Заметки",
    projects:   "Проекты",
    tasks:      "Задачи",
  } as Record<string, string>)[props.currentTab] || props.currentTab;
});

const shortId = computed(() => props.companyId.slice(0, 8) + "…");
</script>

<template>
  <aside class="ap-panel">
    <header class="ap-head">
      <span class="ap-title">
        <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor"
             stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <rect x="2" y="3" width="12" height="3" rx="1" />
          <rect x="2" y="10" width="12" height="3" rx="1" />
          <line x1="4" y1="4.5" x2="5" y2="4.5" />
          <line x1="4" y1="11.5" x2="5" y2="11.5" />
        </svg>
        API · {{ tabLabel }}
      </span>
      <button class="ap-refresh" @click="refresh" title="Обновить" :disabled="loading">↻</button>
    </header>

    <div v-if="loading && endpoints.length === 0" class="ap-loading">Загружаю…</div>
    <div v-else-if="error" class="ap-error">{{ error }}</div>
    <div v-else-if="endpoints.length === 0" class="ap-empty">
      Для этой вкладки нет company-scoped endpoints
    </div>

    <div v-else class="ap-list">
      <EndpointCard
        v-for="e in endpoints"
        :key="e.method + ':' + e.path"
        :endpoint="e"
        compact
        @try="emit('open-try', $event)"
      />
    </div>

    <!-- Substitutions hint -->
    <div class="ap-subs">
      <div class="ap-subs-label">Подставлено в пути</div>
      <div class="ap-subs-row">
        <code class="mono">{id}</code>
        <span class="ap-subs-arrow">→</span>
        <code class="mono ap-subs-val">{{ shortId }}</code>
      </div>
    </div>

    <p class="ap-foot-hint">
      Все endpoints требуют JWT, кроме помеченных <span class="ap-hint-public">public</span>.
    </p>
  </aside>
</template>

<style scoped>
.ap-panel {
  background: rgba(127, 119, 221, 0.03);
  border-left: 0.5px solid #F1EFE8;
  width: 320px;
  flex-shrink: 0;
  padding: 14px 12px;
  display: flex; flex-direction: column; gap: 10px;
  overflow-y: auto;
}

.ap-head { display: flex; align-items: center; justify-content: space-between; }
.ap-title {
  display: flex; align-items: center; gap: 6px;
  font-size: 11px; font-weight: 500; color: var(--p-deep);
  letter-spacing: -0.01em;
}
.ap-refresh {
  background: transparent; border: none; cursor: pointer;
  color: var(--t3, var(--t-muted)); font-size: 14px; padding: 0 6px; border-radius: 4px;
  transition: color 120ms, background 120ms;
}
.ap-refresh:hover:not(:disabled) { color: var(--p-deep); background: rgba(127,119,221,.08); }
.ap-refresh:disabled { opacity: .5; cursor: wait; }

.ap-loading,
.ap-empty,
.ap-error { font-size: 11.5px; color: var(--t3, var(--t-muted)); padding: 18px 8px; text-align: center; }
.ap-error { color: #A82C2B; background: rgba(226,75,74,.06); border-radius: 8px; }

.ap-list { display: flex; flex-direction: column; gap: 6px; }

.ap-subs {
  background: white;
  border: 0.5px solid #F1EFE8;
  border-radius: 8px;
  padding: 8px 10px;
  display: flex; flex-direction: column; gap: 4px;
}
.ap-subs-label { font-size: 9.5px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--t3, var(--t-muted)); font-weight: 500; }
.ap-subs-row   { display: flex; align-items: baseline; gap: 6px; font-size: 11px; }
.ap-subs-arrow { color: #C8C7C0; }
.ap-subs-val   { color: var(--p-deep); font-weight: 600; }
.mono          { font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 11px; }

.ap-foot-hint {
  font-size: 10.5px;
  color: var(--t3, var(--t-muted));
  line-height: 1.4;
  margin: 0;
  padding-top: 8px;
  border-top: 0.5px dashed rgba(15,23,60,.06);
}
.ap-hint-public {
  display: inline-block;
  background: rgba(29,158,117,.10);
  color: #0F6E56;
  padding: 1px 6px;
  border-radius: 6px;
  font-weight: 500;
}
</style>
