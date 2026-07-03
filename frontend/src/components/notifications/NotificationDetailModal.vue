<script setup lang="ts">
/**
 * NotificationDetailModal — премиум-карточка деталей уведомления (для тех, что
 * нельзя открыть как задачу/проект). Показывает: действие, объект, подробности,
 * кто (реальное имя), где, когда. Монтируется один раз в App.vue.
 */
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { useNotificationDetail } from "@/composables/useNotificationDetail";
import { describeNotification, NOTIF_ICON_PATHS } from "@/composables/useNotificationMeta";
import { useEntityEditor } from "@/composables/useEntityEditor";
import ActorAvatar from "@/components/ActorAvatar.vue";
import { useFormatters } from "@/composables/useFormatters";
import { api } from "@/api/client";
import { notificationsApi, type NotificationAuditDetail } from "@/api/notifications";
import ModalShell from "@/components/ModalShell.vue";

const nd = useNotificationDetail();
const fmt = useFormatters();
const router = useRouter();
const entityEditor = useEntityEditor();

// Field-level детали изменения из журнала аудита — «что кто где изменял до
// мелочей». Подтягиваем по клику (без новых уведомлений; объём не растёт).
const auditDetail = ref<NotificationAuditDetail | null>(null);
const auditLoading = ref(false);
watch(() => nd.state.notification?.id, async (id) => {
  auditDetail.value = null;
  if (!id) return;
  auditLoading.value = true;
  try {
    auditDetail.value = await notificationsApi.auditDetail(id);
  } catch { auditDetail.value = null; }
  finally { auditLoading.value = false; }
}, { immediate: true });

// Имя автора — через тот же источник, что и ActorAvatar (/users/card, доступен всем).
const actorCard = ref<any | null>(null);
watch(() => nd.state.notification?.source_user_id, async (id) => {
  actorCard.value = null;
  if (!id) return;
  const cache = (window as any).__uhCache || ((window as any).__uhCache = new Map());
  if (cache.has(id)) { actorCard.value = cache.get(id); return; }
  try {
    const { data } = await api.get("/users/card", { params: { id } });
    cache.set(id, data); actorCard.value = data;
  } catch { actorCard.value = null; }
}, { immediate: true });

const n = computed(() => nd.state.notification);
const d = computed(() => (n.value ? describeNotification(n.value as any) : null));
const iconPath = (k?: string) => NOTIF_ICON_PATHS[k || "bell"] || NOTIF_ICON_PATHS.bell;

const MODULE_LABELS: Record<string, string> = {
  tasks: "Задачи", finance: "Финансы", business_plan: "Бизнес-план", kpi: "KPI",
  esg: "ESG", governance: "Корп. управление", ratings: "Рейтинги",
  investment: "Инвест-проекты", procurement: "Закупки", companies: "Компании",
  moderation: "Модерация", notification: "Уведомления", auth: "Вход и сессии",
};
const moduleLabel = computed(() => {
  const m = n.value?.source_module || "";
  return MODULE_LABELS[m] || m || "—";
});
const actorName = computed(() => {
  if (!n.value?.source_user_id) return "Система";
  return actorCard.value?.full_name || "Пользователь";
});
const whenAbs = computed(() => (n.value ? fmt.fmtDateTime(n.value.created_at) : ""));

// Убираем шаблонный префикс «Имя глагол … «Название»: » — название уже в
// заголовке, показываем только осмысленную часть (саму суть изменения).
const bodyText = computed(() => {
  const b = (n.value?.body || "").trim();
  if (!b) return "";
  // Общий случай: «<актор> <глагол> ... «Название»: <суть>» → берём <суть>.
  const m = b.match(/^.{0,90}?«[^»]+»:\s*([\s\S]+)$/);
  if (m && m[1] && m[1].trim().length > 2) return m[1].trim();
  return b;
});
const showBody = computed(() => {
  const b = bodyText.value;
  if (!b) return false;
  const dt = d.value?.detail;
  if (dt && dt.kind === "text" && (dt as any).text === b) return false;
  return true;
});

// Ссылка ТОЛЬКО на саму задачу/проект (не на список/страницу модуля).
const sourceLink = computed<string | null>(() => {
  const x = n.value as any; if (!x) return null;
  const lu: string = x.link_url || "";
  if (/\/(tasks|projects)\/[0-9a-fA-F-]{36}/.test(lu)) return lu;
  const src = (x.source_entity_id || "") + " " + ((x.payload as any)?.entity_id || "");
  const m = src.match(/\/(tasks|projects)\/([0-9a-fA-F-]{36})/);
  if (m) return `/${m[1]}/${m[2]}`;
  const et = (x.payload as any)?.entity_type, eid = (x.payload as any)?.entity_id;
  if ((et === "task" || et === "project") && eid) return `/${et}s/${eid}`;
  return null;
});
function openSource() {
  const link = sourceLink.value; if (!link) return;
  nd.close();
  if (entityEditor.openFromLink(link)) return;
  router.push(link);
}
</script>

<template>
  <ModalShell :open="nd.state.open && !!n && !!d" size="sm" @close="nd.close()">
    <template v-if="n && d" #header>
      <div class="ndm-head">
        <span class="ndm-ic" :style="{ background: d.accent + '16', color: d.accent }">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" v-html="iconPath(d.icon)" />
        </span>
        <div class="ndm-head-main">
          <span class="ndm-verb" :style="{ color: d.accent, background: d.accent + '14' }">{{ d.verb }}</span>
          <span class="ndm-when">{{ whenAbs }}</span>
        </div>
      </div>
    </template>

    <div v-if="n && d" :style="{ '--accent': d.accent }">
      <!-- Объект -->
      <div v-if="d.entity" class="ndm-entity">{{ d.entity }}</div>

      <!-- Подробности действия -->
      <div v-if="d.detail" class="ndm-detail">
        <template v-if="d.detail.kind === 'status' || d.detail.kind === 'deadline'">
          <span class="ndm-pill ndm-pill-old">{{ (d.detail as any).from }}</span>
          <svg class="ndm-arrow" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
          <span class="ndm-pill ndm-pill-new" :style="{ color: d.accent, background: d.accent + '16' }">{{ (d.detail as any).to }}</span>
        </template>
        <span v-else class="ndm-text">{{ (d.detail as any).text }}</span>
      </div>

      <!-- Мета: кто / где / когда -->
      <div class="ndm-meta">
        <div class="ndm-meta-row">
          <svg class="ndm-meta-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
          <span class="ndm-meta-l">Кто</span>
          <span class="ndm-meta-v ndm-who">
            <ActorAvatar :user-id="n.source_user_id || ''" :size="20" />
            <span>{{ actorName }}</span>
          </span>
        </div>
        <div class="ndm-meta-row">
          <svg class="ndm-meta-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
          <span class="ndm-meta-l">Где</span>
          <span class="ndm-meta-v">{{ moduleLabel }}</span>
        </div>
        <div class="ndm-meta-row">
          <svg class="ndm-meta-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>
          <span class="ndm-meta-l">Когда</span>
          <span class="ndm-meta-v">{{ whenAbs }}</span>
        </div>
      </div>

      <!-- Field-level детали из журнала аудита: что именно и где изменено -->
      <div v-if="auditLoading" class="ndm-audit ndm-audit-load">Загрузка деталей изменения…</div>
      <div v-else-if="auditDetail && auditDetail.found" class="ndm-audit">
        <div class="ndm-body-lbl">Что изменилось</div>
        <!-- Где: раздел + таблица + запись -->
        <div class="ndm-audit-where">
          <span v-if="auditDetail.section" class="ndm-tag ndm-tag-sec">{{ auditDetail.section }}</span>
          <span v-if="auditDetail.table" class="ndm-tag">{{ auditDetail.table }}</span>
          <span v-if="auditDetail.entity_label" class="ndm-audit-ent">{{ auditDetail.entity_label }}</span>
        </div>
        <!-- Построчный diff: поле · было → стало (или значение) -->
        <div v-if="auditDetail.changes.length" class="ndm-diff">
          <div v-for="(c, i) in auditDetail.changes" :key="i" class="ndm-diff-row">
            <span class="ndm-diff-f">{{ c.label }}</span>
            <span v-if="c.old != null || c.new != null" class="ndm-diff-v">
              <span class="ndm-pill ndm-pill-old">{{ c.old ?? '—' }}</span>
              <svg class="ndm-arrow" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
              <span class="ndm-pill ndm-pill-new" :style="{ color: d.accent, background: d.accent + '16' }">{{ c.new ?? '—' }}</span>
            </span>
            <span v-else class="ndm-diff-single">{{ c.value }}</span>
          </div>
        </div>
        <!-- Примечание аудита, если diff-полей нет -->
        <div v-else-if="auditDetail.notes" class="ndm-audit-note">{{ auditDetail.notes }}</div>
      </div>

      <!-- Полный текст уведомления -->
      <div v-if="showBody" class="ndm-bodywrap">
        <div class="ndm-body-lbl">Подробнее</div>
        <div class="ndm-body">{{ bodyText }}</div>
      </div>
    </div>

    <template v-if="n && d" #footer>
      <button v-if="sourceLink" class="ndm-src" @click="openSource">
        {{ sourceLink.includes('/projects/') ? 'Открыть проект' : 'Открыть задачу' }}
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
      </button>
      <button class="ndm-ok" @click="nd.close()">Закрыть</button>
    </template>
  </ModalShell>
</template>

<style scoped>
.ndm-head { display: flex; align-items: center; gap: 13px; }
.ndm-ic {
  width: 44px; height: 44px; border-radius: 13px; flex-shrink: 0;
  display: inline-flex; align-items: center; justify-content: center;
}
.ndm-head-main { display: flex; flex-direction: column; align-items: flex-start; gap: 5px; min-width: 0; }
.ndm-verb {
  font-size: 11px; font-weight: 700; letter-spacing: .02em; text-transform: uppercase;
  padding: 3px 10px; border-radius: 999px;
}
.ndm-when { font-size: 11px; color: var(--t3, #888780); font-variant-numeric: tabular-nums; }

.ndm-entity {
  font-size: 15px; font-weight: 600; color: var(--t1, #1E2A4A);
  line-height: 1.45; letter-spacing: -.01em; margin-bottom: 12px;
}
.ndm-detail { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; margin-bottom: 14px; }
.ndm-pill {
  font-size: 11.5px; font-weight: 600; line-height: 1;
  padding: 5px 11px; border-radius: 7px; font-variant-numeric: tabular-nums; white-space: nowrap;
}
.ndm-pill-old { color: var(--t3, #888780); background: #F1F2F6; }
.ndm-arrow { color: var(--t4, #B4B2A9); flex-shrink: 0; }
.ndm-text {
  font-size: 12.5px; color: var(--t2, #4B5468); line-height: 1.5;
  border-left: 2.5px solid var(--accent, #E5E7EB); padding-left: 10px;
}

.ndm-meta {
  background: var(--bg2, #F8F9FC); border: 1px solid var(--border, #EEF0F5); border-radius: 12px;
  padding: 4px 14px; display: flex; flex-direction: column;
}
.ndm-meta-row { display: flex; align-items: center; gap: 9px; padding: 9px 0; }
.ndm-meta-row + .ndm-meta-row { border-top: 1px solid var(--border, #EEF0F5); }
.ndm-meta-ic { width: 14px; height: 14px; color: var(--t4, #B4B2A9); flex-shrink: 0; }
.ndm-meta-l { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; color: var(--t3, #888780); width: 52px; flex-shrink: 0; }
.ndm-meta-v { font-size: 12.5px; color: var(--t1, #1E2A4A); font-weight: 500; margin-left: auto; text-align: right; }
.ndm-who { display: inline-flex; align-items: center; gap: 7px; }

.ndm-bodywrap { margin-top: 14px; }
.ndm-body-lbl { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; color: var(--t3, #888780); margin-bottom: 5px; }
.ndm-body {
  font-size: 12.5px; color: var(--t2, #4B5468); line-height: 1.6;
  max-height: 150px; overflow-y: auto;
}

/* ── Field-level детали из журнала аудита ── */
.ndm-audit { margin-top: 14px; }
.ndm-audit-load { font-size: 12px; color: var(--t3, #888780); font-style: italic; }
.ndm-audit-where { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-bottom: 9px; }
.ndm-tag {
  font-size: 10.5px; font-weight: 600; color: var(--t2, #4B5468);
  background: #F1F2F6; border-radius: 6px; padding: 2px 8px; white-space: nowrap;
}
.ndm-tag-sec { color: #534AB7; background: rgba(127,119,221,.12); }
.ndm-audit-ent { font-size: 12px; font-weight: 500; color: var(--t1, #1E2A4A); }
.ndm-diff { display: flex; flex-direction: column; gap: 7px; }
.ndm-diff-row {
  display: flex; align-items: center; flex-wrap: wrap; gap: 6px 10px;
  padding: 7px 10px; background: var(--bg2, #F8F9FC);
  border: 1px solid var(--border, #EEF0F5); border-radius: 9px;
}
.ndm-diff-f { font-size: 11px; font-weight: 600; color: var(--t3, #888780); min-width: 92px; flex-shrink: 0; }
.ndm-diff-v { display: inline-flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-left: auto; }
.ndm-diff-single { font-size: 12px; color: var(--t1, #1E2A4A); font-weight: 500; margin-left: auto; text-align: right; word-break: break-word; }
.ndm-audit-note { font-size: 12.5px; color: var(--t2, #4B5468); line-height: 1.55; }

.ndm-src {
  display: inline-flex; align-items: center; gap: 5px; margin-right: auto;
  font-size: 12px; font-weight: 600; font-family: inherit;
  color: var(--p-deep, #534AB7); background: transparent;
  border: 1px solid var(--border-hard, #E5E7EB); border-radius: 10px;
  padding: 8px 14px; cursor: pointer; transition: background .12s, border-color .12s;
}
.ndm-src:hover { background: rgba(127,119,221,.08); border-color: rgba(127,119,221,.35); }
.ndm-src svg { opacity: .8; }
.ndm-ok {
  font-size: 12.5px; font-weight: 600; font-family: inherit; color: #fff;
  background: linear-gradient(135deg, #8B7FFF 0%, #6C5CE7 100%);
  border: none; border-radius: 10px; padding: 9px 20px; cursor: pointer;
  box-shadow: 0 3px 12px rgba(108, 92, 231, 0.34); transition: transform .14s, box-shadow .14s;
}
.ndm-ok:hover { transform: translateY(-1px); box-shadow: 0 6px 18px rgba(108, 92, 231, 0.45); }
.ndm-ok:active { transform: translateY(0); }

@media (max-width: 480px) {
  .ndm-entity { font-size: 14px; }
}
</style>
