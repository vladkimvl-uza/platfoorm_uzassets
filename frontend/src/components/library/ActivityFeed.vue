<script setup lang="ts">
/**
 * ActivityFeed — recent changes feed for a company.
 * Each row has a colored sync-source dot, actor, action label, and relative time.
 */
import { computed } from "vue";
import SyncIndicator from "./SyncIndicator.vue";
import type { LibraryActivityEntry } from "@/api/companyLibrary";

const props = defineProps<{ entries: LibraryActivityEntry[] }>();

const visible = computed(() => (props.entries || []).slice(0, 10));

function fmtTimeAgo(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const m = Math.floor((Date.now() - d.getTime()) / 60_000);
  if (m < 1) return "только что";
  if (m < 60) return `${m} мин назад`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} ч назад`;
  const days = Math.floor(h / 24);
  if (days < 31) return `${days} дн назад`;
  return d.toLocaleDateString("ru-RU");
}

function actionLabel(action: string): string {
  return ({
    "CREATE": "создал",
    "UPDATE": "изменил",
    "DELETE": "удалил",
    "VIEW":   "просмотрел",
    "MUTATE": "изменил",
  } as Record<string, string>)[(action || "").toUpperCase()] || action;
}
</script>

<template>
  <article class="af-card">
    <header class="af-card-h">
      Последняя активность
      <span class="af-card-h-sub">· изменения в этой компании</span>
    </header>
    <ul v-if="visible.length" class="af-list">
      <li v-for="(e, i) in visible" :key="i" class="af-row">
        <SyncIndicator :source-module="e.module" :size="7" />
        <div class="af-row-text">
          <div class="af-row-line1">
            <b v-if="e.actor_email" class="af-row-actor">{{ e.actor_email }}</b>
            <span class="af-row-action">{{ actionLabel(e.action) }}</span>
            <span v-if="e.field_code" class="af-row-field">«{{ e.field_code }}»</span>
          </div>
          <div class="af-row-time">{{ fmtTimeAgo(e.ts) }}</div>
        </div>
      </li>
    </ul>
    <div v-else class="af-empty">Изменений пока нет</div>
  </article>
</template>

<style scoped>
.af-card {
  background: white;
  border-radius: 12px;
  padding: 14px 16px;
  border: 0.5px solid #F1EFE8;
}
.af-card-h {
  font-size: 10.5px; font-weight: 500; letter-spacing: 0.06em; text-transform: uppercase;
  color: #888780;
  display: flex; align-items: baseline; gap: 6px;
  margin-bottom: 10px;
}
.af-card-h-sub { text-transform: none; letter-spacing: 0; font-size: 10px; color: #C8C7C0; font-weight: 400; }

.af-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 8px; }
.af-row {
  display: grid; grid-template-columns: 12px 1fr; gap: 10px;
  align-items: flex-start;
  padding: 4px 0;
  border-bottom: 0.5px dashed rgba(15,23,60,.05);
  font-size: 12px;
}
.af-row:last-child { border-bottom: none; }
.af-row .cl-sync-dot { margin-top: 4px; }
.af-row-text   { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.af-row-line1  { display: flex; align-items: baseline; gap: 5px; flex-wrap: wrap; }
.af-row-actor  { font-weight: 500; color: #1E2A4A; }
.af-row-action { color: #888780; }
.af-row-field  { color: #534AB7; font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 11px; }
.af-row-time   { font-size: 10.5px; color: #C8C7C0; }

.af-empty { padding: 16px 0; text-align: center; color: #888780; font-size: 12px; }
</style>
