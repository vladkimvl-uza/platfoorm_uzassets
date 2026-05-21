<script setup lang="ts">
/**
 * CompanyActivityFeed — лента активности по конкретной компании.
 * Use in CompanyWorkspace Overview tab.
 *
 * Backend filters by per-company scope (allowed_company_ids):
 * user without access gets 403 — этот компонент тогда показывает empty state.
 */
import { ref, onMounted, computed, watch } from "vue";
import { api } from "@/api/client";

interface ActivityItem {
  kind: "task_history" | "audit_log";
  ts: string;
  actor: string;
  action: string;
  field?: string | null;
  old_value?: string | null;
  new_value?: string | null;
  title?: string;
  entity_id: string;
  entity_type: string;
  is_critical: boolean;
  notes?: string;
}

const props = defineProps<{
  companyCode: string;
  days?: number;
  limit?: number;
}>();

const items = ref<ActivityItem[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

async function load() {
  if (!props.companyCode) return;
  loading.value = true;
  error.value = null;
  try {
    const { data } = await api.get(`/companies/${props.companyCode}/activity`, {
      params: { limit: props.limit ?? 30, days: props.days ?? 7 },
    });
    items.value = data.items || [];
  } catch (e: any) {
    if (e?.response?.status === 403) {
      // User doesn't have access — show empty silently
      items.value = [];
    } else {
      error.value = e?.response?.data?.detail || "Не удалось загрузить активность";
    }
  } finally {
    loading.value = false;
  }
}

onMounted(load);
watch(() => props.companyCode, load);

function fmtTime(iso: string): string {
  const d = new Date(iso);
  const now = Date.now();
  const diffSec = Math.floor((now - d.getTime()) / 1000);
  if (diffSec < 60) return "только что";
  if (diffSec < 3600) return Math.floor(diffSec / 60) + " мин назад";
  if (diffSec < 86400) return Math.floor(diffSec / 3600) + " ч назад";
  const days = Math.floor(diffSec / 86400);
  if (days === 1) return "вчера";
  if (days < 7) return days + " дн назад";
  return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "short" });
}

function actionLabel(it: ActivityItem): string {
  // Pretty labels for common actions
  if (it.action === "status_changed") return "сменил статус";
  if (it.action === "field_updated") return `обновил «${it.field || "поле"}»`;
  if (it.action === "archived") return "архивировал";
  if (it.action === "result_set") return "отметил результат";
  if (it.action === "result_cleared") return "снял результат";
  if (it.action === "CREATE") return "создал";
  if (it.action === "UPDATE") return "обновил";
  if (it.action === "DELETE") return "удалил";
  if (it.action === "VIEW") return "просмотрел";
  if (it.action === "FAILED") return "ошибка доступа";
  if (it.action.startsWith("login.")) return "вход";
  return it.action;
}

function actionColor(it: ActivityItem): string {
  if (it.is_critical) return "#E24B4A";
  if (it.action === "DELETE" || it.action === "archived") return "#EF9F27";
  if (it.action === "CREATE" || it.action === "result_set") return "#1D9E75";
  if (it.action.startsWith("FAIL") || it.action === "FAILED") return "#E24B4A";
  return "#7F77DD";
}

const empty = computed(() => !loading.value && !error.value && items.value.length === 0);
</script>

<template>
  <div class="caf-root">
    <header class="caf-header">
      <div class="caf-title">Лента активности</div>
      <button class="caf-refresh" :disabled="loading" @click="load" title="Обновить">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" :class="{ 'caf-spin': loading }">
          <polyline points="23 4 23 10 17 10"/>
          <polyline points="1 20 1 14 7 14"/>
          <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
        </svg>
      </button>
    </header>

    <div v-if="loading && items.length === 0" class="caf-state">Загрузка…</div>
    <div v-else-if="error" class="caf-state caf-state-err">{{ error }}</div>
    <div v-else-if="empty" class="caf-state caf-state-empty">
      Нет активности за последние {{ days ?? 7 }} дней
    </div>
    <ul v-else class="caf-list">
      <li v-for="(it, i) in items" :key="i" class="caf-item">
        <span class="caf-dot" :style="{ background: actionColor(it) }"></span>
        <div class="caf-row">
          <div class="caf-line1">
            <span class="caf-actor">{{ it.actor }}</span>
            <span class="caf-action">{{ actionLabel(it) }}</span>
            <span v-if="it.title" class="caf-target" :title="it.title">{{ it.title }}</span>
          </div>
          <div class="caf-line2">
            <span class="caf-ts">{{ fmtTime(it.ts) }}</span>
            <span v-if="it.kind === 'task_history' && it.old_value && it.new_value"
                  class="caf-diff" :title="`${it.old_value} → ${it.new_value}`">
              {{ String(it.old_value).slice(0, 30) }} → {{ String(it.new_value).slice(0, 30) }}
            </span>
            <span v-else-if="it.notes" class="caf-note">{{ it.notes.slice(0, 100) }}</span>
          </div>
        </div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.caf-root {
  background: white;
  border: 0.5px solid #E5E7EB;
  border-radius: 11px;
  padding: 14px 16px;
  display: flex; flex-direction: column;
  min-height: 280px;
}
.caf-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.caf-title {
  font-size: 11px; font-weight: 500; color: #888780;
  text-transform: uppercase; letter-spacing: .08em;
}
.caf-refresh {
  background: transparent; border: none; cursor: pointer;
  color: #888780; padding: 4px; font-family: inherit;
}
.caf-refresh:hover { color: #7F77DD; }
.caf-spin { animation: caf-spin 1s linear infinite; }
@keyframes caf-spin { to { transform: rotate(360deg); } }

.caf-state {
  flex: 1; display: flex; align-items: center; justify-content: center;
  font-size: 12.5px; color: #888780; padding: 24px;
}
.caf-state-err { color: #E24B4A; }
.caf-state-empty { font-style: italic; }

.caf-list {
  list-style: none; padding: 0; margin: 0;
  display: flex; flex-direction: column; gap: 2px;
  max-height: 420px; overflow-y: auto;
}
.caf-item {
  display: grid; grid-template-columns: 8px 1fr;
  gap: 10px; padding: 8px 4px;
  border-radius: 6px;
  transition: background .1s;
}
.caf-item:hover { background: #FAFAFC; }
.caf-dot {
  width: 8px; height: 8px; border-radius: 50%;
  margin-top: 6px;
}
.caf-row { min-width: 0; }
.caf-line1 {
  display: flex; align-items: baseline; gap: 6px;
  font-size: 12px; color: #1E2A4A;
  flex-wrap: wrap;
}
.caf-actor { font-weight: 500; color: #534AB7; }
.caf-action { color: #888780; }
.caf-target {
  font-weight: 500;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  max-width: 100%;
}
.caf-line2 {
  font-size: 10.5px; color: #888780;
  margin-top: 2px;
  display: flex; gap: 8px;
}
.caf-ts { font-variant-numeric: tabular-nums; }
.caf-diff, .caf-note {
  color: #534AB7;
  font-family: ui-monospace, monospace;
  font-size: 10px;
  max-width: 100%;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
</style>
