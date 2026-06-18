<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { broadcastsApi, formatRelativeTime, type BroadcastAnalytics } from "@/api/admin_broadcasts";
import { useConfirm } from "@/composables/useConfirm";
import BIcon from "./BIcon.vue";

const { confirmDialog } = useConfirm();

const props = defineProps<{ templateId: string }>();

const data = ref<BroadcastAnalytics | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);

async function load() {
  loading.value = true;
  error.value = null;
  try { data.value = await broadcastsApi.analytics(props.templateId); }
  catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
  finally { loading.value = false; }
}

onMounted(load);
watch(() => props.templateId, load);

const deliveredPct = computed(() => {
  if (!data.value || !data.value.last_recipients) return 0;
  return Math.round((data.value.last_delivered / data.value.last_recipients) * 100);
});
const readPct = computed(() => {
  if (!data.value || !data.value.last_recipients) return 0;
  return Math.round((data.value.last_read / data.value.last_recipients) * 100);
});
const ackedPct = computed(() => {
  if (!data.value || !data.value.last_recipients) return 0;
  return Math.round((data.value.last_acked / data.value.last_recipients) * 100);
});
const distMax = computed(() => {
  if (!data.value) return 1;
  const vals = Object.values(data.value.response_distribution || {});
  return Math.max(1, ...vals);
});

async function resendNonResponders() {
  if (!data.value) return;
  if (!(await confirmDialog({ message: `Повторить отправку ${data.value.non_responders.length} не ответившим?` }))) return;
  try {
    await broadcastsApi.sendNow(props.templateId);
    await load();
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
}

function initials(name: string | null, email: string): string {
  if (!name) return email.slice(0, 2).toUpperCase();
  const parts = name.split(" ").filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}
</script>

<template>
  <div class="ba-wrap">
    <div v-if="error" class="ba-err">{{ error }}</div>
    <div v-if="loading && !data" class="ba-loading">Загрузка…</div>

    <template v-else-if="data">
      <div class="ba-header">
        <div class="ba-h-l">
          <div class="ba-eyebrow">Активность · {{ data.dispatches_total }} запусков</div>
          <div class="ba-title">{{ data.template_name }}</div>
          <div class="ba-meta">
            <span v-if="data.last_run_at">Последняя: <b>{{ formatRelativeTime(data.last_run_at) }}</b></span>
            <span v-if="data.next_run_at"> · следующая: <b>{{ formatRelativeTime(data.next_run_at) }}</b></span>
            <span v-if="!data.last_run_at && !data.next_run_at">Запусков ещё не было</span>
          </div>
        </div>
        <div>
          <span class="ba-status-pill" :class="data.is_active ? 'active' : 'off'">
            {{ data.is_active ? "ACTIVE" : "OFF" }}
          </span>
        </div>
      </div>

      <div class="ba-kpis">
        <div class="ba-kpi">
          <div class="ba-kpi-lbl">Получатели</div>
          <div class="ba-kpi-val">{{ data.last_recipients }}</div>
          <div class="ba-kpi-sub">последний запуск</div>
        </div>
        <div class="ba-kpi">
          <div class="ba-kpi-lbl">Доставлено</div>
          <div class="ba-kpi-val">{{ data.last_delivered }}<span class="ba-kpi-of">/ {{ data.last_recipients }}</span></div>
          <div class="ba-kpi-sub" style="color: #0F6E56;">{{ deliveredPct }}%</div>
        </div>
        <div class="ba-kpi">
          <div class="ba-kpi-lbl">Прочитано</div>
          <div class="ba-kpi-val">{{ data.last_read }}<span class="ba-kpi-of">/ {{ data.last_recipients }}</span></div>
          <div class="ba-kpi-sub" :style="{ color: readPct >= 80 ? '#0F6E56' : '#854F0B' }">{{ readPct }}%</div>
        </div>
        <div class="ba-kpi ba-kpi-acked">
          <div class="ba-kpi-lbl">Подтверждено</div>
          <div class="ba-kpi-val">{{ data.last_acked }}<span class="ba-kpi-of">/ {{ data.last_recipients }}</span></div>
          <div class="ba-kpi-sub" :style="{ color: ackedPct >= 80 ? '#0F6E56' : '#854F0B' }">
            {{ ackedPct }}% · ждём {{ Math.max(0, data.last_recipients - data.last_acked) }}
          </div>
        </div>
      </div>

      <div v-if="Object.keys(data.response_distribution).length > 0" class="ba-section">
        <div class="ba-section-hd">Распределение ответов · последний запуск</div>
        <div class="ba-bars">
          <div v-for="(count, key) in data.response_distribution" :key="key" class="ba-bar-row">
            <div class="ba-bar-lbl">{{ key }}</div>
            <div class="ba-bar-track">
              <div class="ba-bar-fill" :style="{ width: ((count / distMax) * 100) + '%' }"></div>
            </div>
            <div class="ba-bar-val">{{ count }}</div>
          </div>
        </div>
      </div>

      <div v-if="data.non_responders.length" class="ba-section ba-section-warn">
        <div class="ba-section-hd ba-section-hd-warn">
          Не ответили · {{ data.non_responders.length }}
        </div>
        <div class="ba-non-responders">
          <span v-for="u in data.non_responders.slice(0, 20)" :key="u.id" class="ba-nr-chip">
            <span class="ba-nr-avatar">{{ initials(u.full_name, u.email) }}</span>
            {{ u.full_name || u.email }}
          </span>
          <span v-if="data.non_responders.length > 20" class="ba-nr-more">+ {{ data.non_responders.length - 20 }} ещё</span>
        </div>
        <div class="ba-actions">
          <button class="ba-btn ba-btn-amber" @click="resendNonResponders">
            <BIcon name="send" :size="13" /> Re-send всем не ответившим
          </button>
        </div>
      </div>

      <div v-if="data.history.length" class="ba-section">
        <div class="ba-section-hd">История запусков</div>
        <table class="ba-history">
          <thead>
            <tr>
              <th>Когда</th>
              <th>Триггер</th>
              <th class="r">Получатели</th>
              <th class="r">Доставлено</th>
              <th class="r">Прочитано</th>
              <th class="r">Ack</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="h in data.history" :key="h.id">
              <td>{{ new Date(h.dispatched_at).toLocaleString("ru-RU", { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) }}</td>
              <td><span class="ba-trig-pill" :class="`trig-${h.trigger}`">{{ h.trigger }}</span></td>
              <td class="r">{{ h.recipients_count }}</td>
              <td class="r">{{ h.delivered_count }}</td>
              <td class="r">{{ h.read_count }}</td>
              <td class="r"><b>{{ h.acked_count }}</b></td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<style scoped>
.ba-wrap { padding: 14px 18px; display: flex; flex-direction: column; gap: 12px; flex: 1; overflow-y: auto; }
.ba-loading { padding: 60px; text-align: center; color: var(--color-text-tertiary); font-size: 13px; }
.ba-err { background: rgba(226,75,74,.08); color: var(--sev-critical); padding: 8px 12px; border-radius: 7px; font-size: 11.5px; }

.ba-header {
  display: flex; justify-content: space-between; align-items: flex-start; gap: 12px;
  padding: 12px 16px;
  background: var(--color-background-primary);
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: 10px;
}
.ba-eyebrow { font-size: 10px; color: var(--color-text-tertiary); text-transform: uppercase; letter-spacing: .07em; }
.ba-title { font-size: 15px; color: var(--color-text-primary); font-weight: 500; margin-top: 3px; }
.ba-meta { font-size: 11px; color: var(--color-text-secondary); margin-top: 4px; }
.ba-status-pill {
  padding: 3px 10px;
  border-radius: 11px;
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: .05em;
}
.ba-status-pill.active { background: rgba(29,158,117,.12); color: #0F6E56; }
.ba-status-pill.off    { background: rgba(136,135,128,.12); color: var(--t3, #5F5E5A); }

.ba-kpis {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px;
}
.ba-kpi {
  background: var(--color-background-primary);
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: 9px;
  padding: 10px 12px;
}
.ba-kpi-lbl { font-size: 9.5px; color: var(--color-text-tertiary); text-transform: uppercase; letter-spacing: .05em; }
.ba-kpi-val {
  font-size: 22px; color: var(--color-text-primary); font-weight: 500;
  font-feature-settings: "tnum"; letter-spacing: -.025em;
  margin-top: 2px;
}
.ba-kpi-of { font-size: 11px; color: var(--color-text-tertiary); font-weight: 400; margin-left: 4px; }
.ba-kpi-sub { font-size: 10px; margin-top: 1px; }
.ba-kpi-acked { background: rgba(29,158,117,.04); border-color: rgba(29,158,117,.2); }

.ba-section {
  background: var(--color-background-primary);
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: 10px;
  overflow: hidden;
}
.ba-section-warn { background: rgba(226,75,74,.03); border-color: rgba(226,75,74,.18); }
.ba-section-hd {
  padding: 9px 14px;
  background: var(--bg2, #FAFAFC);
  border-bottom: 0.5px solid var(--color-border-tertiary);
  font-size: 9.5px;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: .07em;
  font-weight: 500;
}
.ba-section-hd-warn { color: var(--sev-critical); background: rgba(226,75,74,.05); }

.ba-bars { padding: 10px 14px; display: flex; flex-direction: column; gap: 6px; }
.ba-bar-row { display: flex; align-items: center; gap: 8px; font-size: 11.5px; }
.ba-bar-lbl { width: 130px; color: var(--color-text-secondary); }
.ba-bar-track { flex: 1; height: 14px; background: var(--color-background-secondary); border-radius: 7px; overflow: hidden; }
.ba-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #7F77DD, var(--p-deep));
  border-radius: 7px;
  transition: width .35s var(--ease-standard);
}
.ba-bar-val { width: 32px; text-align: right; font-feature-settings: "tnum"; color: var(--color-text-primary); font-weight: 500; }

.ba-non-responders { padding: 10px 14px; display: flex; flex-wrap: wrap; gap: 4px; }
.ba-nr-chip {
  display: inline-flex; align-items: center; gap: 5px;
  background: var(--color-background-primary);
  border: 0.5px solid rgba(226,75,74,.2);
  padding: 3px 9px;
  border-radius: 11px;
  font-size: 10.5px;
  color: var(--color-text-primary);
}
.ba-nr-avatar {
  width: 16px; height: 16px;
  border-radius: 50%;
  background: rgba(212,83,126,.15);
  color: #993556;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 8px; font-weight: 600;
}
.ba-nr-more {
  color: var(--color-text-secondary); font-size: 10.5px;
  align-self: center; margin-left: 4px;
}
.ba-actions { padding: 0 14px 12px; }
.ba-btn {
  border: 0;
  padding: 7px 14px;
  border-radius: 6px;
  font-size: 11.5px;
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
  display: inline-flex; align-items: center; gap: 4px;
}
.ba-btn-amber { background: var(--amber); color: #fff; }
.ba-btn-amber:hover { background: var(--sev-mid); }

.ba-history { width: 100%; border-collapse: separate; border-spacing: 0; }
.ba-history thead th {
  padding: 8px 14px;
  text-align: left;
  font-size: 9px;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: .07em;
  background: var(--bg2, #FAFAFC);
}
.ba-history tbody td {
  padding: 8px 14px;
  font-size: 11.5px;
  color: var(--color-text-primary);
  border-top: 0.5px solid rgba(0,0,0,.04);
  font-feature-settings: "tnum";
}
.ba-history .r { text-align: right; }
.ba-trig-pill {
  padding: 1px 7px;
  border-radius: 3px;
  font-size: 9px;
  font-weight: 600;
  text-transform: lowercase;
}
.ba-trig-pill.trig-schedule { background: rgba(127,119,221,.12); color: var(--p-deep); }
.ba-trig-pill.trig-manual   { background: rgba(29,158,117,.12);  color: #0F6E56; }
.ba-trig-pill.trig-resend   { background: rgba(239,159,39,.15);  color: #854F0B; }
</style>
