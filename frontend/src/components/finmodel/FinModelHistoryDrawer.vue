<script setup lang="ts">
/**
 * FinModelHistoryDrawer — inline drawer над таблицей с audit log активного года.
 * Backed by GET /finmodel/{co}/{year}/audit.
 */
import { computed, ref, watch } from "vue";
import { finmodelApi, type AuditEntry } from "@/api/finmodel";

const props = defineProps<{
  open: boolean;
  companyId: string;
  year: number | null;
}>();

const emit = defineEmits<{
  close: [];
}>();

const items = ref<AuditEntry[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

async function reload() {
  if (!props.open || !props.companyId || !props.year) return;
  loading.value = true;
  error.value = null;
  try {
    const res = await finmodelApi.getAudit(props.companyId, props.year, undefined, 100);
    items.value = res.items;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Ошибка загрузки";
  } finally {
    loading.value = false;
  }
}

watch(() => [props.open, props.companyId, props.year], reload, { immediate: true });

function fmtTs(ts: string): string {
  return new Date(ts).toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "short" });
}

function fmtVal(v: string | null): string {
  if (v == null) return "∅";
  const n = Number(v);
  return Number.isFinite(n) ? n.toLocaleString("ru-RU") : v;
}

const sourceColors: Record<string, string> = {
  manual: "#534AB7",
  excel_import: "#1D9E75",
  forecast: "#EF9F27",
  manual_year_delete: "#C0322F",
};
function srcColor(s: string): string {
  return sourceColors[s] ?? "#888780";
}
</script>

<template>
  <Transition name="fm-drawer">
    <div v-if="open" class="fm-drawer">
      <header class="fm-drawer-head">
        <span class="fm-drawer-cap">История изменений · {{ year }}</span>
        <span class="fm-drawer-count">{{ items.length }} записей</span>
        <button class="fm-drawer-refresh" :disabled="loading" @click="reload">{{ loading ? "Загрузка…" : "Обновить" }}</button>
        <button class="fm-drawer-close" @click="emit('close')" title="Закрыть">×</button>
      </header>

      <div v-if="error" class="fm-drawer-err">{{ error }}</div>
      <div v-else-if="!loading && items.length === 0" class="fm-drawer-empty">
        Изменений по этому году ещё не было.
      </div>
      <ul v-else class="fm-drawer-list">
        <li v-for="e in items" :key="e.id" class="fm-drawer-row">
          <span class="fm-drawer-ts">{{ fmtTs(e.ts) }}</span>
          <span class="fm-drawer-source" :style="`color: ${srcColor(e.source)}; background: ${srcColor(e.source)}1a;`">{{ e.source }}</span>
          <span class="fm-drawer-code">{{ e.row_code }}</span>
          <span class="fm-drawer-vals">
            <span class="fm-v-before">{{ fmtVal(e.value_before) }}</span>
            →
            <span class="fm-v-after">{{ fmtVal(e.value_after) }}</span>
          </span>
        </li>
      </ul>
    </div>
  </Transition>
</template>

<style scoped>
.fm-drawer {
  border-bottom: 0.5px solid #F1EFE8;
  background: #FAFAFC;
}
.fm-drawer-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border-bottom: 0.5px solid #F1EFE8;
}
.fm-drawer-cap {
  font-size: 10px; font-weight: 500;
  color: #888780; letter-spacing: .08em; text-transform: uppercase;
}
.fm-drawer-count { font-size: 10.5px; color: #888780; }
.fm-drawer-refresh {
  margin-left: auto;
  height: 22px; padding: 0 10px;
  background: transparent;
  border: 0.5px solid #E5E7EB;
  border-radius: 5px;
  font-size: 10.5px;
  color: #1E2A4A;
  font-family: inherit;
  cursor: pointer;
}
.fm-drawer-refresh:disabled { opacity: .5; cursor: not-allowed; }
.fm-drawer-close {
  width: 22px; height: 22px;
  background: transparent;
  border: 0.5px solid #E5E7EB;
  border-radius: 5px;
  color: #888780;
  cursor: pointer;
  font-family: inherit;
  font-size: 13px;
  line-height: 1;
}
.fm-drawer-err {
  padding: 12px 14px;
  font-size: 11px;
  color: #C0322F;
}
.fm-drawer-empty {
  padding: 28px 14px;
  text-align: center;
  font-size: 11px;
  color: #888780;
  font-style: italic;
}
.fm-drawer-list {
  list-style: none;
  padding: 0;
  margin: 0;
  max-height: 320px;
  overflow-y: auto;
}
.fm-drawer-row {
  display: grid;
  grid-template-columns: 110px 110px 70px 1fr;
  align-items: center;
  gap: 10px;
  padding: 6px 14px;
  border-bottom: 0.5px solid #F1EFE8;
  font-size: 11px;
}
.fm-drawer-ts {
  font-size: 10px;
  color: #888780;
  font-variant-numeric: tabular-nums;
}
.fm-drawer-source {
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 9.5px;
  font-weight: 500;
  text-align: center;
  text-transform: uppercase;
  letter-spacing: .04em;
}
.fm-drawer-code {
  font-family: ui-monospace, monospace;
  font-size: 10.5px;
  color: #888780;
}
.fm-drawer-vals {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.fm-v-before {
  color: #C0322F;
  text-decoration: line-through;
  text-decoration-color: rgba(192, 50, 47, .4);
  margin-right: 4px;
}
.fm-v-after {
  color: #0F6E56;
  font-weight: 500;
  margin-left: 4px;
}

.fm-drawer-enter-active, .fm-drawer-leave-active {
  transition: max-height .25s ease-out, opacity .15s;
  overflow: hidden;
}
.fm-drawer-enter-from, .fm-drawer-leave-to {
  max-height: 0; opacity: 0;
}
.fm-drawer-enter-to, .fm-drawer-leave-from {
  max-height: 400px; opacity: 1;
}
</style>
