<script setup lang="ts">
/**
 * NotificationDetailModal — карточка деталей уведомления (для тех, что нельзя
 * открыть как задачу/проект). Показывает: действие, объект, подробности,
 * кто, когда, где. Монтируется один раз в App.vue.
 */
import { computed } from "vue";
import { useNotificationDetail } from "@/composables/useNotificationDetail";
import { describeNotification, NOTIF_ICON_PATHS } from "@/composables/useNotificationMeta";
import ActorAvatar from "@/components/ActorAvatar.vue";
import { useFormatters } from "@/composables/useFormatters";

const nd = useNotificationDetail();
const fmt = useFormatters();

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
const whenAbs = computed(() => (n.value ? fmt.fmtDateTime(n.value.created_at) : ""));

function onBackdrop(e: MouseEvent) {
  if (e.target === e.currentTarget) nd.close();
}
</script>

<template>
  <Transition name="ndm">
    <div v-if="nd.state.open && n && d" class="ndm-bg" @click="onBackdrop" @keydown.esc="nd.close()">
      <div class="ndm-card" role="dialog" aria-modal="true" :style="{ '--accent': d.accent }">
        <span class="ndm-stripe"></span>
        <button class="ndm-x" @click="nd.close()" aria-label="Закрыть">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>

        <!-- Действие -->
        <div class="ndm-head">
          <span class="ndm-ic" :style="{ background: d.accent + '16', color: d.accent }">
            <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" v-html="iconPath(d.icon)" />
          </span>
          <div class="ndm-head-main">
            <span class="ndm-verb" :style="{ color: d.accent }">{{ d.verb }}</span>
            <span class="ndm-when">{{ whenAbs }}</span>
          </div>
        </div>

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

        <!-- Мета: кто / где -->
        <div class="ndm-meta">
          <div class="ndm-meta-row">
            <span class="ndm-meta-l">Кто</span>
            <span class="ndm-meta-v ndm-who">
              <ActorAvatar :user-id="n.source_user_id || ''" :size="22" />
              <span>{{ n.source_user_id ? "пользователь" : "Система" }}</span>
            </span>
          </div>
          <div class="ndm-meta-row">
            <span class="ndm-meta-l">Где</span>
            <span class="ndm-meta-v">{{ moduleLabel }}</span>
          </div>
          <div class="ndm-meta-row">
            <span class="ndm-meta-l">Когда</span>
            <span class="ndm-meta-v">{{ whenAbs }}</span>
          </div>
        </div>

        <!-- Полный текст уведомления -->
        <div v-if="n.body && (!d.detail || d.detail.kind !== 'text' || (d.detail as any).text !== n.body)" class="ndm-body">
          {{ n.body }}
        </div>

        <div class="ndm-foot">
          <button class="ndm-ok" @click="nd.close()">Понятно</button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.ndm-bg {
  position: fixed; inset: 0; z-index: 9600;
  background: rgba(15, 18, 40, 0.45); backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center; padding: 16px;
}
.ndm-card {
  position: relative; width: 100%; max-width: 440px;
  background: var(--bg1, #fff); border-radius: 16px;
  padding: 22px 22px 18px;
  box-shadow: 0 28px 70px rgba(15, 23, 60, 0.26), 0 8px 24px rgba(15, 23, 60, 0.10);
  overflow: hidden;
}
.ndm-stripe { position: absolute; top: 0; left: 0; right: 0; height: 4px; background: var(--accent, #7C6FF7); }
.ndm-x {
  position: absolute; top: 12px; right: 12px; width: 28px; height: 28px;
  display: inline-flex; align-items: center; justify-content: center;
  background: transparent; border: none; border-radius: 8px;
  color: var(--t3, #888780); cursor: pointer; transition: background .12s, color .12s;
}
.ndm-x:hover { background: rgba(0,0,0,.05); color: var(--t1, #1E2A4A); }

.ndm-head { display: flex; align-items: center; gap: 12px; margin: 4px 0 14px; }
.ndm-ic {
  width: 40px; height: 40px; border-radius: 11px; flex-shrink: 0;
  display: inline-flex; align-items: center; justify-content: center;
}
.ndm-head-main { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.ndm-verb { font-size: 15px; font-weight: 600; letter-spacing: -.01em; }
.ndm-when { font-size: 11px; color: var(--t3, #888780); }

.ndm-entity {
  font-size: 14px; font-weight: 500; color: var(--t1, #1E2A4A);
  line-height: 1.4; margin-bottom: 10px;
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
  background: var(--bg2, #F9FAFB); border-radius: 11px;
  padding: 10px 14px; display: flex; flex-direction: column; gap: 7px;
}
.ndm-meta-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.ndm-meta-l { font-size: 10px; font-weight: 500; text-transform: uppercase; letter-spacing: .06em; color: var(--t3, #888780); }
.ndm-meta-v { font-size: 12.5px; color: var(--t1, #1E2A4A); font-weight: 500; }
.ndm-who { display: inline-flex; align-items: center; gap: 7px; }

.ndm-body {
  margin-top: 12px; font-size: 12.5px; color: var(--t2, #4B5468); line-height: 1.55;
  max-height: 160px; overflow-y: auto;
}

.ndm-foot { display: flex; justify-content: flex-end; margin-top: 16px; }
.ndm-ok {
  font-size: 12.5px; font-weight: 600; font-family: inherit; color: #fff;
  background: linear-gradient(135deg, #8B7FFF 0%, #6C5CE7 100%);
  border: none; border-radius: 9px; padding: 8px 18px; cursor: pointer;
  box-shadow: 0 3px 12px rgba(108, 92, 231, 0.34); transition: transform .14s, box-shadow .14s;
}
.ndm-ok:hover { transform: translateY(-1px); box-shadow: 0 6px 18px rgba(108, 92, 231, 0.45); }

.ndm-enter-active, .ndm-leave-active { transition: opacity .22s ease; }
.ndm-enter-active .ndm-card { animation: ndmIn .34s cubic-bezier(.34, 1.2, .64, 1); }
.ndm-enter-from, .ndm-leave-to { opacity: 0; }
@keyframes ndmIn { from { opacity: 0; transform: translateY(14px) scale(.97); } to { opacity: 1; transform: none; } }
</style>
