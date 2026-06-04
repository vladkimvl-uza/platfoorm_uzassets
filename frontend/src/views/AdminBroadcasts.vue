<script setup lang="ts">
/**
 * AdminBroadcasts.vue — главная страница рассылок.
 * Левая колонка: список шаблонов. Правая: composer ИЛИ analytics в зависимости от выбора.
 */
import { computed, onMounted, ref } from "vue";
import {
  broadcastsApi,
  ACK_MODE_LABELS, PRIORITY_PILL, formatRelativeTime,
  type Template, type TemplateListItem, type TemplatePayload,
} from "@/api/admin_broadcasts";
import BroadcastComposer from "@/components/broadcasts/BroadcastComposer.vue";
import BroadcastAnalytics from "@/components/broadcasts/BroadcastAnalytics.vue";
import BIcon from "@/components/broadcasts/BIcon.vue";

const list = ref<TemplateListItem[]>([]);
const selectedId = ref<string | null>(null);
const view = ref<"composer" | "analytics">("composer");
const loading = ref(false);
const error = ref<string | null>(null);

async function loadList() {
  loading.value = true;
  try { const r = await broadcastsApi.listTemplates(); list.value = r.items; }
  catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
  finally { loading.value = false; }
}

onMounted(loadList);

function selectTemplate(id: string, v: "composer" | "analytics" = "composer") {
  selectedId.value = id;
  view.value = v;
}

async function createNew() {
  const draft: TemplatePayload = {
    name: "Новая рассылка",
    is_active: false,
    type: "announcement",
    priority: "normal",
    title: "Заголовок рассылки",
    body: "",
    link_url: null,
    attachments: null,
    icon: null,
    color: null,
    target_user_ids: null,
    target_group_codes: null,
    target_role_codes: null,
    target_company_ids: null,
    target_sector_ids: null,
    target_all: false,
    target_filter_expr: null,
    ack_mode: "none",
    ack_question: null,
    ack_options: null,
    is_sticky: false,
    ack_deadline_hours: null,
    auto_resend_hours: null,
    escalate_to_manager: false,
    show_site_banner_on_overdue: false,
    schedule_mode: "oneshot",
    schedule_config: null,
    schedule_start_at: null,
    schedule_end_at: null,
  };
  try {
    const t = await broadcastsApi.createTemplate(draft);
    await loadList();
    selectTemplate(t.id, "composer");
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
}

async function toggle(item: TemplateListItem, ev: Event) {
  ev.stopPropagation();
  try {
    await broadcastsApi.toggleTemplate(item.id);
    await loadList();
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
}

function onSaved() { loadList(); }
function onDeleted() {
  selectedId.value = null;
  loadList();
}

const scheduleSummary = (t: TemplateListItem): string => {
  if (t.schedule_mode === "oneshot") return "Однократно";
  if (t.schedule_mode === "interval") {
    if (t.next_run_at) return `→ ${new Date(t.next_run_at).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}`;
    return "Повторяющееся";
  }
  return t.schedule_mode;
};
</script>

<template>
  <div class="abr-page">
    <div class="abr-topbar">
      <div class="abr-tb-l">
        <span class="abr-tb-icn">
          <BIcon name="speakerphone" :size="18" />
        </span>
        <div>
          <div class="abr-eyebrow">Owner panel · уведомления</div>
          <div class="abr-title">Кастомные рассылки</div>
        </div>
      </div>
      <div class="abr-tb-r">
        <span class="abr-counter">{{ list.length }} шаблонов</span>
      </div>
    </div>

    <div v-if="error" class="abr-err">
      {{ error }}
      <button class="abr-err-x" @click="error = null">×</button>
    </div>

    <div class="abr-grid">
      <div class="abr-list-col">
        <button class="abr-new" @click="createNew">
          <BIcon name="plus" :size="15" /> Новая рассылка
        </button>

        <div v-if="loading && list.length === 0" class="abr-empty">Загрузка…</div>
        <div v-else-if="!list.length" class="abr-empty">
          <BIcon name="speakerphone" :size="26" style="color: var(--t3, #94A3B8);" />
          <div>Рассылок ещё нет</div>
          <div style="font-size: 10.5px; margin-top: 2px; color: var(--t3, #94A3B8);">Создайте первую — она появится здесь</div>
        </div>

        <div v-else class="abr-list">
          <div v-for="t in list" :key="t.id" class="abr-row"
               :class="{ active: selectedId === t.id, off: !t.is_active }"
               @click="selectTemplate(t.id)">
            <div class="abr-row-hd">
              <span class="abr-row-name">{{ t.name }}</span>
              <button class="abr-row-toggle" :class="{ on: t.is_active }" @click="toggle(t, $event)">
                {{ t.is_active ? "ON" : "OFF" }}
              </button>
            </div>
            <div class="abr-row-tags">
              <span class="abr-pri-pill"
                    :style="{ color: PRIORITY_PILL[t.priority].color, background: PRIORITY_PILL[t.priority].bg }">
                {{ PRIORITY_PILL[t.priority].label }}
              </span>
              <span v-if="t.is_sticky" class="abr-sticky-pill">
                <BIcon name="pin" :size="10" /> sticky
              </span>
              <span v-if="t.ack_mode !== 'none'" class="abr-ack-pill">{{ ACK_MODE_LABELS[t.ack_mode] }}</span>
            </div>
            <div class="abr-row-meta">{{ scheduleSummary(t) }}</div>
            <div v-if="t.total_dispatches > 0" class="abr-row-stats">
              <BIcon name="send" :size="11" />
              {{ t.total_dispatches }} запусков · {{ t.total_acks_lifetime }} откликов
            </div>
          </div>
        </div>
      </div>

      <div class="abr-detail-col">
        <div v-if="!selectedId" class="abr-no-sel">
          <BIcon name="arrow-left" :size="18" style="opacity:.4;" />
          Выберите рассылку слева или создайте новую
        </div>

        <template v-else>
          <div class="abr-view-tabs">
            <button class="abr-vt" :class="{ active: view === 'composer' }" @click="view = 'composer'">
              <BIcon name="edit" :size="14" /> Редактор
            </button>
            <button class="abr-vt" :class="{ active: view === 'analytics' }" @click="view = 'analytics'">
              <BIcon name="chart-bar" :size="14" /> Аналитика
            </button>
          </div>

          <BroadcastComposer
            v-if="view === 'composer'"
            :template-id="selectedId"
            @saved="onSaved"
            @deleted="onDeleted"
          />
          <BroadcastAnalytics
            v-else
            :template-id="selectedId"
          />
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.abr-page {
  display: flex;
  flex-direction: column;
  min-height: 100%;
  background: var(--color-background-tertiary);
}

.abr-topbar {
  background: linear-gradient(95deg, #1E2A4A 0%, #2D3760 60%, #4B477E 100%);
  padding: 14px 22px;
  display: flex; justify-content: space-between; align-items: center;
}
.abr-tb-l { display: flex; align-items: center; gap: 11px; }
.abr-tb-icn {
  width: 34px; height: 34px;
  border-radius: 8px;
  background: rgba(127,119,221,.2);
  color: #fff;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 18px;
}
.abr-eyebrow {
  font-size: 10px;
  color: rgba(255,255,255,.55);
  text-transform: uppercase;
  letter-spacing: .08em;
  font-weight: 500;
}
.abr-title { font-size: 16px; color: #fff; font-weight: 500; margin-top: 2px; }
.abr-counter {
  background: rgba(255,255,255,.1);
  color: #fff;
  padding: 4px 10px;
  border-radius: 14px;
  font-size: 11px;
  font-feature-settings: "tnum";
}

.abr-err {
  margin: 8px 18px 0;
  background: rgba(226,75,74,.08);
  border: 0.5px solid rgba(226,75,74,.3);
  color: var(--sev-critical);
  padding: 8px 14px;
  border-radius: 8px;
  font-size: 11.5px;
  display: flex; justify-content: space-between; align-items: center;
}
.abr-err-x { background: transparent; border: 0; color: var(--sev-critical); cursor: pointer; font-size: 18px; }

.abr-grid {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 0;
  flex: 1;
}

/* List column */
.abr-list-col {
  border-right: 0.5px solid var(--color-border-tertiary);
  background: var(--color-background-primary);
  display: flex; flex-direction: column;
  overflow-y: auto;
}
.abr-new {
  margin: 12px 14px;
  background: #7F77DD;
  color: #fff;
  border: 0;
  padding: 8px 14px;
  border-radius: 7px;
  cursor: pointer;
  font-family: inherit;
  font-size: 11.5px;
  font-weight: 500;
  display: inline-flex; align-items: center; gap: 5px; justify-content: center;
}
.abr-empty {
  padding: 50px 16px;
  text-align: center;
  color: var(--color-text-tertiary);
  font-size: 11.5px;
  display: flex; flex-direction: column; align-items: center; gap: 6px;
}
.abr-list { display: flex; flex-direction: column; }
.abr-row {
  padding: 10px 14px;
  border-bottom: 0.5px solid rgba(0,0,0,.04);
  cursor: pointer;
  transition: background .12s;
  position: relative; overflow: hidden;
}
.abr-row:hover { background: rgba(127,119,221,.03); }
.abr-row.active { background: rgba(127,119,221,.08); }
.abr-row.active::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 2px; background: #7F77DD;
  animation: uzaStripeDrawIn .4s var(--ease-standard) both;
  transform-origin: left center;
  pointer-events: none;
}
.abr-row.off { opacity: .55; }
.abr-row-hd {
  display: flex; justify-content: space-between; align-items: center; gap: 6px;
  margin-bottom: 5px;
}
.abr-row-name {
  font-size: 12.5px;
  color: var(--color-text-primary);
  font-weight: 500;
  flex: 1; min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.abr-row-toggle {
  background: rgba(0,0,0,.06);
  color: var(--color-text-tertiary);
  border: 0;
  padding: 2px 7px;
  border-radius: 3px;
  font-size: 9px;
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
  flex-shrink: 0;
}
.abr-row-toggle.on { background: var(--green); color: #fff; }

.abr-row-tags { display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 4px; }
.abr-pri-pill {
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 9px;
  font-weight: 500;
  letter-spacing: .04em;
  text-transform: lowercase;
}
.abr-sticky-pill {
  background: rgba(212,83,126,.12);
  color: #993556;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 9px;
  font-weight: 500;
  display: inline-flex; align-items: center; gap: 3px;
}
.abr-ack-pill {
  background: rgba(127,119,221,.08);
  color: var(--p-deep);
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 9px;
}

.abr-row-meta {
  font-size: 10px;
  color: var(--color-text-tertiary);
}
.abr-row-stats {
  font-size: 10px;
  color: var(--color-text-secondary);
  margin-top: 3px;
  display: inline-flex; align-items: center; gap: 4px;
}

/* Detail column */
.abr-detail-col {
  display: flex; flex-direction: column;
  background: var(--color-background-tertiary);
  overflow-y: auto;
}
.abr-no-sel {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  flex: 1;
  color: var(--color-text-tertiary);
  font-size: 13px;
}

.abr-view-tabs {
  display: flex; gap: 0;
  padding: 0 18px;
  background: var(--color-background-primary);
  border-bottom: 0.5px solid var(--color-border-tertiary);
}
.abr-vt {
  background: transparent;
  border: 0;
  padding: 9px 14px 11px;
  font-family: inherit;
  font-size: 11.5px;
  color: var(--color-text-secondary);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  display: inline-flex; align-items: center; gap: 5px;
}
.abr-vt:hover { color: var(--color-text-primary); }
.abr-vt.active {
  color: var(--color-text-primary);
  border-bottom-color: #7F77DD;
  font-weight: 500;
}
</style>
