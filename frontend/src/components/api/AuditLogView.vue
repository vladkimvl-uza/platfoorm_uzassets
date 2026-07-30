<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import BIcon from "@/components/broadcasts/BIcon.vue";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import ModalShell from "@/components/ModalShell.vue";
import { auditApi, httpStatusColor, type AuditEvent } from "@/api/partners";
import { useI18n } from "@/composables/useI18n";
import { getCurrentIntlLocale } from "@/locale/i18n";
const { t } = useI18n();


const events = ref<AuditEvent[]>([]);
const total  = ref(0);
const loading = ref(false);
const error  = ref<string | null>(null);

const filters = ref({
  hours: 24 as number | null,
  module: "",
  action: "",
  only_critical: false,
  only_api_key: false,
  search: "",
});
const page = ref(1);
const per_page = 50;

const detailOpen = ref<AuditEvent | null>(null);

async function reload() {
  loading.value = true; error.value = null;
  try {
    const r = await auditApi.events({
      hours: filters.value.hours ?? undefined,
      module: filters.value.module || undefined,
      action: filters.value.action || undefined,
      only_critical: filters.value.only_critical,
      only_api_key: filters.value.only_api_key,
      search: filters.value.search || undefined,
      page: page.value,
      per_page,
    });
    events.value = r.items;
    total.value  = r.total;
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
  finally { loading.value = false; }
}

onMounted(reload);
watch([() => filters.value.hours, () => filters.value.module, () => filters.value.only_critical,
       () => filters.value.only_api_key], () => { page.value = 1; reload(); });

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleString(getCurrentIntlLocale(), { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
function fmtRel(iso: string): string {
  const d = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (d < 60) return t('{value0}с', { value0: d });
  if (d < 3600) return t('{value0}мин', { value0: Math.floor(d / 60) });
  if (d < 86400) return t('{value0}ч', { value0: Math.floor(d / 3600) });
  return t('{value0}д', { value0: Math.floor(d / 86400) });
}
</script>

<template>
  <div class="al-wrap">
    <UzaStateBlock v-if="error" state="error" variant="banner" :text="error" dismissible @dismiss="error = null" />

    <div class="al-filters">
      <div class="al-fl">
        <label>{{ t('Период') }}</label>
        <select v-model.number="filters.hours">
          <option :value="1">{{ t('1 час') }}</option>
          <option :value="6">{{ t('6 часов') }}</option>
          <option :value="24">{{ t('24 часа') }}</option>
          <option :value="168">{{ t('7 дней') }}</option>
          <option :value="720">{{ t('30 дней') }}</option>
          <option :value="null">{{ t('всё время') }}</option>
        </select>
      </div>
      <div class="al-fl">
        <label>{{ t('Модуль') }}</label>
        <input v-model="filters.module" placeholder="e.g. api_keys, broadcasts"/>
      </div>
      <div class="al-fl">
        <label>Action</label>
        <input v-model="filters.action" placeholder="e.g. create, update"/>
      </div>
      <div class="al-fl al-fl-stretch">
        <label>{{ t('Поиск') }}</label>
        <input v-model="filters.search" @input="reload" placeholder="entity_label, email…"/>
      </div>
      <label class="al-chk">
        <input v-model="filters.only_critical" type="checkbox"/>
        {{ t('Только critical') }}
      </label>
      <label class="al-chk">
        <input v-model="filters.only_api_key" type="checkbox"/>
        {{ t('Только API-key auth') }}
      </label>
      <button class="al-btn" @click="reload">
        <BIcon name="refresh" :size="14" /> {{ t('Обновить') }}
      </button>
    </div>

    <div class="al-bar">
      <div>{{ total }} {{ t('событий') }}</div>
      <div v-if="loading" style="color: var(--color-text-tertiary); font-size: 11px;">
        <BIcon name="loader-2" :size="14" /> {{ t('загрузка…') }}
      </div>
    </div>

    <UzaStateBlock v-if="!events.length" state="empty" variant="block" :text="t('Журнал пуст для выбранных фильтров')">
      <template #icon><BIcon name="history" :size="14" /></template>
    </UzaStateBlock>

    <table v-else class="al-tbl uza-table">
      <thead>
        <tr>
          <th>{{ t('Время') }}</th>
          <th>Actor</th>
          <th>Action</th>
          <th>{{ t('Модуль') }}</th>
          <th>{{ t('Сущность') }}</th>
          <th>HTTP</th>
          <th>Long.</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="e in events" :key="e.id" @click="detailOpen = e" class="al-row"
            :class="{ 'al-critical': e.is_critical, 'al-via-key': !!e.api_key_id }">
          <td class="al-t">
            <div>{{ fmtTime(e.created_at) }}</div>
            <div class="al-rel">{{ fmtRel(e.created_at) }} {{ t('назад') }}</div>
          </td>
          <td>
            <div v-if="e.api_key_id" style="color: #534AB7;"><BIcon name="key" :size="14" /> API key</div>
            <div v-else>{{ e.actor_email || "—" }}</div>
            <div v-if="e.actor_role" style="font-size: 9.5px; color: var(--color-text-tertiary);">{{ e.actor_role }}</div>
          </td>
          <td><code class="al-ac">{{ e.action }}</code></td>
          <td>{{ e.module || "—" }}</td>
          <td class="al-ent">
            <div v-if="e.entity_label">{{ e.entity_label }}</div>
            <div v-else-if="e.entity_type">{{ e.entity_type }} #{{ (e.entity_id || "").slice(0, 8) }}</div>
            <div v-else style="color: var(--color-text-tertiary);">—</div>
          </td>
          <td>
            <span v-if="e.http_status !== null" class="al-http" :style="{ color: httpStatusColor(e.http_status), background: httpStatusColor(e.http_status) + '15' }">
              {{ e.http_method }} {{ e.http_status }}
            </span>
            <span v-else style="color: var(--color-text-tertiary); font-size: 10px;">—</span>
          </td>
          <td class="al-num">{{ e.duration_ms !== null ? `${e.duration_ms}ms` : "—" }}</td>
          <td>
            <span v-if="e.is_critical" class="al-crit-mark" title="critical">!</span>
          </td>
        </tr>
      </tbody>
    </table>

    <!-- Detail modal — канон ModalShell -->
    <ModalShell :open="!!detailOpen" size="md" @close="detailOpen = null">
      <template v-if="detailOpen" #header>
        <div style="display:flex; align-items:center; gap:8px; width:100%;">
          <code class="al-ac" style="font-size: 11px;">{{ detailOpen.action }}</code>
          <span v-if="detailOpen.is_critical" class="al-crit-mark">!</span>
          <span style="font-size: 10px; color: var(--color-text-tertiary); margin-left:auto;">{{ detailOpen.id.slice(0, 8) }}</span>
        </div>
      </template>
      <template v-if="detailOpen">
        <div class="al-detail-grid">
            <div><span>{{ t('Время') }}</span><code>{{ fmtTime(detailOpen.created_at) }}</code></div>
            <div><span>Actor</span><code>{{ detailOpen.actor_email || (detailOpen.api_key_id ? `API key ${detailOpen.api_key_id.slice(0,8)}` : "—") }}</code></div>
            <div><span>{{ t('Модуль') }}</span><code>{{ detailOpen.module || "—" }}</code></div>
            <div><span>Action</span><code>{{ detailOpen.action }}</code></div>
            <div><span>{{ t('Сущность') }}</span><code>{{ detailOpen.entity_type || "—" }}{{ detailOpen.entity_id ? ` #${detailOpen.entity_id.slice(0,8)}` : "" }}</code></div>
            <div><span>HTTP</span><code>{{ detailOpen.http_method || "—" }} {{ detailOpen.http_status ?? "—" }}</code></div>
            <div><span>IP</span><code>{{ detailOpen.ip_address || "—" }}</code></div>
            <div><span>{{ t('Длительность') }}</span><code>{{ detailOpen.duration_ms !== null ? `${detailOpen.duration_ms}ms` : "—" }}</code></div>
          </div>
      </template>
      <template #footer>
        <button class="al-btn" @click="detailOpen = null">{{ t('Закрыть') }}</button>
      </template>
    </ModalShell>
  </div>
</template>

<style scoped>
.al-wrap { flex: 1; display: flex; flex-direction: column; background: var(--color-background-tertiary); padding: 14px 18px; overflow-y: auto; }

.al-filters { display: flex; gap: 8px; align-items: flex-end; flex-wrap: wrap; padding: 12px 14px; background: var(--color-background-primary); border: 0.5px solid var(--color-border-tertiary); border-radius: 8px; margin-bottom: 10px; }
.al-fl { display: flex; flex-direction: column; gap: 3px; }
.al-fl label { font-size: 9.5px; color: var(--color-text-tertiary); text-transform: uppercase; letter-spacing: .05em; }
.al-fl input, .al-fl select { padding: 5px 9px; border: 0.5px solid var(--color-border-tertiary); border-radius: 5px; font-size: 11.5px; font-family: inherit; outline: none; min-width: 140px; }
.al-fl-stretch { flex: 1; min-width: 200px; }
.al-fl-stretch input { width: 100%; }
.al-chk { display: flex; align-items: center; gap: 4px; font-size: 11px; color: var(--color-text-secondary); padding: 4px 0; cursor: pointer; }
.al-btn { background: var(--color-background-primary); border: 0.5px solid var(--color-border-tertiary); padding: 6px 12px; border-radius: 6px; font-size: 11.5px; cursor: pointer; font-family: inherit; color: var(--color-text-secondary); display: inline-flex; align-items: center; gap: 4px; }
.al-btn:hover { background: rgba(127,119,221,.05); }

.al-bar { display: flex; justify-content: space-between; align-items: center; padding: 6px 4px; font-size: 11px; color: var(--color-text-secondary); }

.al-tbl { width: 100%; border-collapse: collapse; background: var(--color-background-primary); border: 0.5px solid var(--color-border-tertiary); border-radius: 8px; overflow: hidden; }
/* th/td база — из глобального .uza-table; здесь только спец-состояния строк */
.al-row { cursor: pointer; }
.al-row:hover { background: rgba(127,119,221,.03); }
.al-row.al-critical td { background: rgba(226,75,74,.04); }
.al-row.al-via-key td:first-child { position: relative; }
.al-row.al-via-key td:first-child::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 2px; background: #7F77DD;
  animation: uzaStripeDrawIn .4s var(--ease-standard) both;
  transform-origin: left center;
  pointer-events: none;
}
.al-t { font-size: 10.5px; }
.al-rel { font-size: 9.5px; color: var(--color-text-tertiary); }
.al-ac { font-family: var(--font-mono, monospace); font-size: 10.5px; background: rgba(127,119,221,.08); color: var(--p-deep); padding: 1px 6px; border-radius: 3px; }
.al-http { font-family: var(--font-mono, monospace); padding: 2px 7px; border-radius: 4px; font-size: 9.5px; font-weight: 600; }
.al-num { font-feature-settings: "tnum"; font-size: 11px; color: var(--color-text-secondary); }
.al-ent { font-size: 11px; max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.al-crit-mark { background: var(--sev-high); color: #fff; padding: 0 5px; border-radius: 50%; font-size: 11px; font-weight: 600; display: inline-block; min-width: 16px; text-align: center; }

.al-modal-bg { position: fixed; inset: 0; z-index: 1000; background: rgba(15,18,40,.45); -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; padding: 20px; }
.al-modal { background: var(--color-background-primary); width: 100%; max-width: 580px; border-radius: 12px; overflow: hidden; box-shadow: 0 24px 64px rgba(15,23,60,.18); }
.al-modal-hd { padding: 12px 18px; background: linear-gradient(90deg, rgba(127,119,221,.06), transparent); border-bottom: 0.5px solid var(--color-border-tertiary); font-size: 12px; color: var(--color-text-primary); display: flex; justify-content: space-between; align-items: center; }
.al-modal-body { padding: 14px 18px; }
.al-modal-footer { padding: 11px 18px; background: var(--bg2, #FAFAFC); border-top: 0.5px solid var(--color-border-tertiary); display: flex; gap: 6px; justify-content: flex-end; }
.al-detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 7px; }
.al-detail-grid > div { display: flex; gap: 9px; align-items: baseline; font-size: 11.5px; padding: 3px 0; }
.al-detail-grid > div > span { color: var(--color-text-tertiary); font-size: 9.5px; text-transform: uppercase; letter-spacing: .04em; min-width: 90px; padding-top: 2px; }
.al-detail-grid code { font-family: var(--font-mono, monospace); font-size: 10.5px; color: var(--color-text-primary); }
</style>
