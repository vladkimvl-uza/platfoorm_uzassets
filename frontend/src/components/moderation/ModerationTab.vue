<script setup lang="ts">
/**
 * ModerationTab — top-level wrapper inside RBAC v2 "Модерация" tab.
 * Renders 5 sub-tabs: rules / moderators / submitted / queue / settings.
 */
import { computed, onMounted, ref, watch } from "vue";
import BIcon from "@/components/broadcasts/BIcon.vue";
import { useRoute, useRouter } from "vue-router";
import { moderationApi, type ModerationOverview } from "@/api/moderation";
import ModerationQueue from "./ModerationQueue.vue";
import ModerationRulesEditor from "./ModerationRulesEditor.vue";
import ModerationModerators from "./ModerationModerators.vue";
import ModerationSubmittedUsers from "./ModerationSubmittedUsers.vue";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();


type SubTab = "queue" | "rules" | "moderators" | "submitted";

const route = useRoute();
const router = useRouter();

const VALID: SubTab[] = ["queue", "rules", "moderators", "submitted"];
const initial = (route.query.sub_tab as SubTab) || "queue";
const subTab = ref<SubTab>(VALID.includes(initial) ? initial : "queue");

const overview = ref<ModerationOverview | null>(null);
const loading = ref(false);
const overviewError = ref<string | null>(null);

async function loadOverview() {
  loading.value = true;
  overviewError.value = null;
  try { overview.value = await moderationApi.overview(); }
  catch (e: any) {
    overviewError.value = e?.response?.data?.detail || t('Не удалось загрузить сводку модерации');
  }
  finally { loading.value = false; }
}

onMounted(loadOverview);

watch(subTab, (v) => {
  router.replace({ query: { ...route.query, sub_tab: v } });
});

const openSubmissionId = computed(() => (route.query.open as string) || null);
</script>

<template>
  <div class="mod-tab">
    <div class="mod-subtabs">
      <button class="mod-st" :class="{ active: subTab === 'rules' }" @click="subTab = 'rules'">
        <BIcon name="route" :size="14" />
        {{ t('Правила') }}
        <span v-if="overview" class="mod-st-cnt">{{ overview.rules_active_count }}</span>
      </button>
      <button class="mod-st" :class="{ active: subTab === 'moderators' }" @click="subTab = 'moderators'">
        <BIcon name="user-check" :size="14" />
        {{ t('Модераторы') }}
        <span v-if="overview" class="mod-st-cnt">{{ overview.moderators_count }}</span>
      </button>
      <button class="mod-st" :class="{ active: subTab === 'submitted' }" @click="subTab = 'submitted'">
        <BIcon name="user-exclamation" :size="14" />
        {{ t('Подмодерируемые') }}
        <span v-if="overview" class="mod-st-cnt">{{ overview.external_users_count }}</span>
      </button>
      <button class="mod-st" :class="{ active: subTab === 'queue' }" @click="subTab = 'queue'">
        <BIcon name="inbox" :size="14" />
        {{ t('Очередь') }}
        <span v-if="overview && overview.pending > 0" class="mod-st-cnt mod-st-cnt-hot">{{ overview.pending }}</span>
      </button>
    </div>

    <!-- Скелет резервирует место (нет прыжка layout); ошибка не глотается в console. -->
    <div v-if="loading && !overview" class="mod-overview-strip" aria-hidden="true">
      <div v-for="n in 4" :key="n" class="mod-ov-card" style="min-height:52px;opacity:.45;"></div>
    </div>
    <div v-else-if="overviewError && !overview" style="font-size:12px;color:#993D3D;padding:8px 12px;">
      {{ overviewError }}
    </div>

    <div v-if="overview" class="mod-overview-strip">
      <div class="mod-ov-card">
        <span class="mod-ov-label">{{ t('Ожидают') }}</span>
        <span class="mod-ov-val mod-ov-pending">{{ overview.pending }}</span>
      </div>
      <div class="mod-ov-card">
        <span class="mod-ov-label">{{ t('На рассмотрении') }}</span>
        <span class="mod-ov-val mod-ov-review">{{ overview.under_review }}</span>
      </div>
      <div class="mod-ov-card">
        <span class="mod-ov-label">{{ t('Сегодня одобрено') }}</span>
        <span class="mod-ov-val mod-ov-approved">{{ overview.approved_today }}</span>
      </div>
      <div class="mod-ov-card">
        <span class="mod-ov-label">{{ t('Сегодня отклонено') }}</span>
        <span class="mod-ov-val mod-ov-rejected">{{ overview.rejected_today }}</span>
      </div>
      <div class="mod-ov-card">
        <span class="mod-ov-label">{{ t('Средн. время') }}</span>
        <span class="mod-ov-val">
          {{ overview.avg_resolution_hours !== null ? t('{value0} ч', { value0: overview.avg_resolution_hours.toFixed(1) }) : "—" }}
        </span>
      </div>
      <div class="mod-ov-card mod-ov-mine">
        <span class="mod-ov-label">{{ t('У меня') }}</span>
        <span class="mod-ov-val">{{ overview.my_pending_count }}</span>
      </div>
    </div>

    <div class="mod-body">
      <ModerationQueue v-if="subTab === 'queue'"
                       :open-submission-id="openSubmissionId"
                       @change="loadOverview" />
      <ModerationRulesEditor v-else-if="subTab === 'rules'" @change="loadOverview" />
      <ModerationModerators v-else-if="subTab === 'moderators'" />
      <ModerationSubmittedUsers v-else-if="subTab === 'submitted'" @change="loadOverview" />
    </div>
  </div>
</template>

<style scoped>
.mod-tab { display: flex; flex-direction: column; }

.mod-subtabs {
  display: flex; gap: 4px;
  padding: 10px 16px 0;
  border-bottom: 0.5px solid var(--color-border-tertiary);
  background: var(--bg2, #FAFAFC);
  overflow-x: auto;
}
.mod-st {
  background: transparent; border: 0;
  padding: 7px 11px 9px;
  border-bottom: 2px solid transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-family: inherit;
  font-size: 12px;
  display: inline-flex; align-items: center; gap: 5px;
  transition: color .12s;
}
.mod-st:hover { color: var(--color-text-primary); }
.mod-st.active { color: var(--color-text-primary); border-bottom-color: #7F77DD; font-weight: 500; }
.mod-st-cnt {
  background: rgba(127,119,221,.12); color: var(--p-deep);
  padding: 1px 6px; border-radius: 9px;
  font-size: 9.5px; font-weight: 600;
}
.mod-st-cnt-hot {
  background: var(--sev-high); color: #fff;
}

.mod-overview-strip {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 6px;
  padding: 10px 16px;
  border-bottom: 0.5px solid var(--color-border-tertiary);
  background: var(--color-background-primary);
}
.mod-ov-card {
  background: var(--color-background-secondary);
  padding: 7px 10px;
  border-radius: 6px;
  display: flex; flex-direction: column; gap: 1px;
}
.mod-ov-label {
  font-size: 9px;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: .05em;
}
.mod-ov-val {
  font-size: 17px;
  font-weight: 500;
  font-feature-settings: "tnum";
  color: var(--color-text-primary);
}
.mod-ov-pending  { color: #854F0B; }
.mod-ov-review   { color: #185FA5; }
.mod-ov-approved { color: #0F6E56; }
.mod-ov-rejected { color: var(--sev-critical); }
.mod-ov-mine { background: rgba(127,119,221,.06); border: 0.5px solid rgba(127,119,221,.2); }

.mod-body { padding: 14px 16px 18px; }

.mod-settings { display: flex; flex-direction: column; gap: 12px; }
.mod-settings-card {
  background: var(--color-background-primary);
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: 10px;
  overflow: hidden;
}
.mod-card-hd {
  padding: 10px 14px;
  background: var(--bg2, #FAFAFC);
  border-bottom: 0.5px solid var(--color-border-tertiary);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: .07em;
  color: var(--color-text-tertiary);
  font-weight: 500;
}
.mod-settings-body { padding: 12px 14px; display: flex; flex-direction: column; gap: 9px; }
.mod-set-row {
  display: flex; justify-content: space-between; align-items: center;
  padding: 6px 0;
  border-bottom: 0.5px dashed rgba(0,0,0,.04);
  font-size: 12px;
}
.mod-set-row:last-child { border-bottom: 0; }
.mod-set-label { color: var(--color-text-secondary); }
.mod-set-input { color: var(--color-text-primary); font-feature-settings: "tnum"; }

.mod-switch { position: relative; display: inline-block; width: 30px; height: 16px; cursor: pointer; }
.mod-switch input { opacity: 0; width: 0; height: 0; }
.mod-switch-tr { position: absolute; inset: 0; background: #D3D1C7; border-radius: 9px; transition: background .2s; }
.mod-switch-tr::before { content: ""; position: absolute; top: 2px; left: 2px; width: 12px; height: 12px; background: var(--bg1, #fff); border-radius: 50%; transition: left .2s; }
.mod-switch input:checked + .mod-switch-tr { background: var(--green); }
.mod-switch input:checked + .mod-switch-tr::before { left: 16px; }
</style>