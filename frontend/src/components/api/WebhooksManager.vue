<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import BIcon from "@/components/broadcasts/BIcon.vue";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import {
  webhooksApi, statusPill, httpStatusPill,
  type WebhookSubscription, type WebhookSubscriptionCreated,
  type WebhookDelivery, type WebhookEventDef, type WebhookStats, type DeliveryStatus,
} from "@/api/webhooks";
import { apiKeysApi, type ServiceAccount } from "@/api/api_catalog";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();


const subs        = ref<WebhookSubscription[]>([]);
const deliveries  = ref<WebhookDelivery[]>([]);
const stats       = ref<WebhookStats | null>(null);
const sas         = ref<ServiceAccount[]>([]);
const events      = ref<Record<string, WebhookEventDef[]>>({});
const selectedSub = ref<WebhookSubscription | null>(null);
const loading     = ref(false);
const error       = ref<string | null>(null);

const showCreate          = ref(false);
const newSub              = ref({
  service_account_id: "", name: "", description: "",
  target_url: "https://example.com/webhook",
  events: new Set<string>(),
  verify_ssl: true,
  max_attempts: 5, timeout_seconds: 10,
});
const plaintextSecret     = ref<WebhookSubscriptionCreated | null>(null);
const deleteTarget        = ref<WebhookSubscription | null>(null);
const showDeliveryDetail  = ref<WebhookDelivery | null>(null);
const filterStatus        = ref<DeliveryStatus | "">("");

async function loadAll() {
  loading.value = true; error.value = null;
  try {
    const [sR, statR, evR, saR] = await Promise.all([
      webhooksApi.listSubscriptions(),
      webhooksApi.stats(),
      webhooksApi.events(),
      apiKeysApi.listServiceAccounts(),
    ]);
    subs.value = sR.items;
    stats.value = statR;
    events.value = evR.grouped_by_module;
    sas.value = saR.items;
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
  finally { loading.value = false; }
}

async function loadDeliveries() {
  try {
    const opts: any = { limit: 100 };
    if (selectedSub.value) opts.subscription_id = selectedSub.value.id;
    if (filterStatus.value) opts.status = filterStatus.value;
    const r = await webhooksApi.listDeliveries(opts);
    deliveries.value = r.items;
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
}

onMounted(async () => { await loadAll(); await loadDeliveries(); });

function selectSub(s: WebhookSubscription | null) {
  selectedSub.value = s;
  loadDeliveries();
}

function toggleEvent(code: string) {
  if (newSub.value.events.has(code)) newSub.value.events.delete(code);
  else newSub.value.events.add(code);
  newSub.value.events = new Set(newSub.value.events);
}

async function submitCreate() {
  if (!newSub.value.service_account_id) { error.value = t('Выберите service account'); return; }
  if (!newSub.value.name.trim()) { error.value = t('Укажите имя подписки'); return; }
  if (!newSub.value.target_url.startsWith("https://") && !newSub.value.target_url.startsWith("http://")) {
    error.value = t('Target URL должен начинаться с https:// или http://'); return;
  }
  try {
    const created = await webhooksApi.createSubscription({
      service_account_id: newSub.value.service_account_id,
      name: newSub.value.name.trim(),
      description: newSub.value.description.trim() || null,
      target_url: newSub.value.target_url.trim(),
      events: Array.from(newSub.value.events),
      verify_ssl: newSub.value.verify_ssl,
      max_attempts: newSub.value.max_attempts,
      timeout_seconds: newSub.value.timeout_seconds,
    });
    showCreate.value = false;
    plaintextSecret.value = created;
    newSub.value = {
      service_account_id: "", name: "", description: "",
      target_url: "https://example.com/webhook",
      events: new Set(), verify_ssl: true,
      max_attempts: 5, timeout_seconds: 10,
    };
    await loadAll();
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
}

async function toggleActive(s: WebhookSubscription) {
  try {
    await webhooksApi.updateSubscription(s.id, { is_active: !s.is_active });
    await loadAll();
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
}

async function sendTest(s: WebhookSubscription) {
  try {
    await webhooksApi.testSubscription(s.id);
    await loadDeliveries();
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
}

async function confirmDelete() {
  if (!deleteTarget.value) return;
  try {
    await webhooksApi.deleteSubscription(deleteTarget.value.id);
    if (selectedSub.value?.id === deleteTarget.value.id) selectedSub.value = null;
    deleteTarget.value = null;
    await loadAll();
    await loadDeliveries();
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
}

async function replay(d: WebhookDelivery) {
  try {
    await webhooksApi.replayDelivery(d.id);
    await loadDeliveries();
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
}

async function copySecret() {
  if (!plaintextSecret.value) return;
  try { await navigator.clipboard.writeText(plaintextSecret.value.plaintext_secret); } catch {}
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}
function fmtRel(iso: string | null): string {
  if (!iso) return "—";
  const d = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (d < 60) return t('{value0} с назад', { value0: d });
  if (d < 3600) return t('{value0} мин назад', { value0: Math.floor(d / 60) });
  if (d < 86400) return t('{value0} ч назад', { value0: Math.floor(d / 3600) });
  return t('{value0} дн назад', { value0: Math.floor(d / 86400) });
}

const successRatePct = computed(() => {
  if (!stats.value?.last_24h.success_rate && stats.value?.last_24h.success_rate !== 0) return null;
  return Math.round(stats.value.last_24h.success_rate * 100);
});
</script>

<template>
  <div class="wh-wrap">
    <UzaStateBlock v-if="error" state="error" variant="banner" :text="error" dismissible @dismiss="error = null" />

    <div v-if="stats" class="wh-stats">
      <div class="wh-stat">
        <div class="wh-stat-l">{{ t('Подписок') }}</div>
        <div class="wh-stat-v">{{ stats.subscriptions.active }}<span class="wh-stat-tot">/{{ stats.subscriptions.total }}</span></div>
      </div>
      <div class="wh-stat">
        <div class="wh-stat-l">{{ t('В очереди') }}</div>
        <div class="wh-stat-v" :class="{ 'wh-stat-warn': stats.pending_deliveries > 50 }">{{ stats.pending_deliveries }}</div>
      </div>
      <div class="wh-stat">
        <div class="wh-stat-l">{{ t('Доставок · 24ч') }}</div>
        <div class="wh-stat-v">{{ stats.last_24h.total }}</div>
      </div>
      <div class="wh-stat">
        <div class="wh-stat-l">{{ t('Success rate · 24ч') }}</div>
        <div class="wh-stat-v" :style="{ color: (successRatePct ?? 100) >= 95 ? '#0F6E56' : ((successRatePct ?? 0) >= 80 ? '#854F0B' : '#A32D2D') }">
          {{ successRatePct === null ? "—" : `${successRatePct}%` }}
        </div>
      </div>
      <div class="wh-stat" style="flex: 0; margin-left: auto;">
        <button class="wh-btn wh-btn-primary" @click="showCreate = true">
          <BIcon name="plus" :size="14" /> {{ t('Новая подписка') }}
        </button>
      </div>
    </div>

    <div class="wh-body">

      <!-- Left: subscriptions list -->
      <div class="wh-side">
        <div class="wh-side-hd">{{ t('Подписки') }} {{ subs.length ? `· ${subs.length}` : "" }}</div>
      <UzaStateBlock v-if="!subs.length" state="empty" variant="block" :title="t('Нет подписок')" :desc="t('Создайте первую')">
          <template #icon><BIcon name="webhook" :size="14" /></template>
        </UzaStateBlock>
        <div v-else class="wh-sub-list">
          <div class="wh-sub-all" :class="{ active: !selectedSub }" @click="selectSub(null)">
            <span>{{ t('Все подписки') }}</span>
            <span class="wh-c">{{ deliveries.length }}</span>
          </div>
          <div v-for="s in subs" :key="s.id" class="wh-sub" :class="{ active: selectedSub?.id === s.id, off: !s.is_active }"
               @click="selectSub(s)">
            <div class="wh-sub-dot" :style="{ background: s.is_active ? (s.consecutive_failures > 0 ? '#EF9F27' : '#1D9E75') : '#A32D2D' }"></div>
            <div class="wh-sub-info">
              <div class="wh-sub-name">{{ s.name }}</div>
              <div class="wh-sub-url">{{ s.target_url }}</div>
              <div class="wh-sub-meta">
                <span>{{ s.events.length }} events</span>
                <span v-if="s.total_failures > 0" style="color: #A32D2D;">{{ s.total_failures }} fail</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Right: delivery log + detail -->
      <div class="wh-main">
        <div v-if="selectedSub" class="wh-sel-hd">
          <div>
            <div class="wh-sel-name">{{ selectedSub.name }}</div>
            <div class="wh-sel-url"><code>{{ selectedSub.target_url }}</code></div>
            <div class="wh-sel-meta">
              <span class="wh-pill" :style="{ color: selectedSub.is_active ? '#0F6E56' : '#A32D2D', background: selectedSub.is_active ? 'rgba(29,158,117,.12)' : 'rgba(226,75,74,.1)' }">
                {{ selectedSub.is_active ? "active" : "disabled" }}
              </span>
              <span>secret: <code>{{ t(selectedSub.secret_hint) }}</code></span>
              <span>{{ selectedSub.events.join(", ") || t('(нет events)') }}</span>
              <span v-if="selectedSub.disabled_reason" style="color: #A32D2D;">{{ t('причина:') }} {{ selectedSub.disabled_reason }}</span>
            </div>
          </div>
          <div class="wh-sel-actions">
            <button class="wh-btn" @click="sendTest(selectedSub)">
              <BIcon name="send" :size="14" /> {{ t('Тест') }}
            </button>
            <button class="wh-btn" @click="toggleActive(selectedSub)">
              <BIcon :name="selectedSub.is_active ? 'player-pause' : 'player-play'" :size="14" />
              {{ selectedSub.is_active ? t('Остановить') : t('Включить') }}
            </button>
            <button class="wh-btn wh-btn-danger" @click="deleteTarget = selectedSub">
              <BIcon name="trash" :size="14" />
            </button>
          </div>
        </div>

        <div class="wh-log-hd">
          <div class="wh-log-t">{{ t('Журнал доставки') }} {{ selectedSub ? `· ${selectedSub.name}` : t('· все') }}</div>
          <select v-model="filterStatus" @change="loadDeliveries" class="wh-filter">
            <option value="">{{ t('Все статусы') }}</option>
            <option value="pending">pending</option>
            <option value="succeeded">succeeded</option>
            <option value="failed">retry</option>
            <option value="exhausted">exhausted</option>
          </select>
          <button class="wh-btn" @click="loadDeliveries" :title="t('Обновить')">
            <BIcon name="refresh" :size="14" />
          </button>
        </div>

        <UzaStateBlock v-if="!deliveries.length" state="empty" variant="block" :text="t('Журнал пуст')">
          <template #icon><BIcon name="history" :size="14" /></template>
        </UzaStateBlock>

        <table v-else class="wh-deliv">
          <thead>
            <tr>
              <th>{{ t('Время') }}</th>
              <th>Event</th>
              <th>{{ t('Статус') }}</th>
              <th>HTTP</th>
              <th>{{ t('Попытка') }}</th>
              <th>{{ t('Длит.') }}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="d in deliveries" :key="d.id" @click="showDeliveryDetail = d" class="wh-deliv-row">
              <td class="wh-time">
                <div>{{ fmtDate(d.created_at) }}</div>
                <div style="font-size: 9.5px; color: var(--color-text-tertiary);">{{ fmtRel(d.created_at) }}</div>
              </td>
              <td><code class="wh-evc">{{ d.event_code }}</code><span v-if="d.is_replay" class="wh-replay-tag">replay</span></td>
              <td>
                <span class="wh-pill" :style="{ color: statusPill(d.status).color, background: statusPill(d.status).bg }">
                  {{ t(statusPill(d.status).label) }}
                </span>
              </td>
              <td>
                <span v-if="d.http_status !== null" class="wh-pill"
                      :style="{ color: httpStatusPill(d.http_status).color, background: httpStatusPill(d.http_status).bg }">
                  {{ d.http_status }}
                </span>
                <span v-else style="color: var(--color-text-tertiary); font-size: 10px;">—</span>
              </td>
              <td class="wh-num">{{ d.attempt_number }}</td>
              <td class="wh-num">{{ d.duration_ms ? `${d.duration_ms}ms` : "—" }}</td>
              <td>
                <button v-if="d.status === 'exhausted' || d.status === 'failed'" class="wh-icon-btn"
                        title="Replay" @click.stop="replay(d)">
                  <BIcon name="refresh" :size="14" />
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ───── Modal: create subscription ───── -->
    <div v-if="showCreate" class="wh-modal-bg" @click.self="showCreate = false">
      <div class="wh-modal" style="max-width: 680px;">
        <div class="wh-modal-hd">{{ t('Новая webhook подписка') }}</div>
        <div class="wh-modal-body">
          <div class="wh-grid">
            <div class="wh-field">
              <label>Service account</label>
              <select v-model="newSub.service_account_id">
                <option value="">{{ t('— выберите —') }}</option>
                <option v-for="sa in sas" :key="sa.id" :value="sa.id" :disabled="!sa.is_active">
                  {{ sa.full_name || sa.email }}{{ sa.is_active ? "" : " (disabled)" }}
                </option>
              </select>
            </div>
            <div class="wh-field">
              <label>{{ t('Имя подписки') }}</label>
              <input v-model="newSub.name" placeholder="ERP integration · prod"/>
            </div>
          </div>
          <div class="wh-field">
            <label>Target URL</label>
            <input v-model="newSub.target_url" placeholder="https://erp.example.com/webhooks/uzassets"/>
          </div>
          <div class="wh-field">
            <label>{{ t('Описание') }}</label>
            <input v-model="newSub.description" :placeholder="t('(необязательно)')"/>
          </div>
          <div class="wh-grid">
            <div class="wh-field">
              <label>{{ t('Макс попыток') }}</label>
              <input v-model.number="newSub.max_attempts" type="number" min="1" max="12"/>
            </div>
            <div class="wh-field">
              <label>{{ t('Timeout (сек)') }}</label>
              <input v-model.number="newSub.timeout_seconds" type="number" min="2" max="60"/>
            </div>
            <div class="wh-field">
              <label class="wh-check">
                <input v-model="newSub.verify_ssl" type="checkbox"/> {{ t('Проверять SSL сертификат') }}
              </label>
            </div>
          </div>

          <div class="wh-field">
            <label>{{ t('События ·') }} {{ newSub.events.size }} {{ t('выбрано') }}</label>
            <div class="wh-evt-tree">
              <div v-for="(items, module) in events" :key="module" class="wh-evt-grp">
                <div class="wh-evt-grp-hd">{{ module }}</div>
                <label v-for="e in items" :key="e.code" class="wh-evt-opt" :class="{ on: newSub.events.has(e.code) }">
                  <input type="checkbox" :checked="newSub.events.has(e.code)" @change="toggleEvent(e.code)"/>
                  <div>
                    <code>{{ e.code }}</code>
                    <div class="wh-evt-lbl">{{ t(e.label) }}</div>
                  </div>
                </label>
              </div>
            </div>
          </div>
        </div>
        <div class="wh-modal-footer">
          <button class="wh-btn wh-btn-ghost" @click="showCreate = false">{{ t('Отмена') }}</button>
          <button class="wh-btn wh-btn-primary" @click="submitCreate">
            <BIcon name="webhook" :size="14" /> {{ t('Создать') }}
          </button>
        </div>
      </div>
    </div>

    <!-- ───── Modal: plaintext secret ───── -->
    <div v-if="plaintextSecret" class="wh-modal-bg">
      <div class="wh-modal" style="max-width: 580px;">
        <div class="wh-modal-hd" style="background: linear-gradient(90deg, rgba(29,158,117,.1), transparent); color: #0F6E56;">
          <BIcon name="check" :size="14" /> {{ t('Подписка создана — сохраните signing secret') }}
        </div>
        <div class="wh-modal-body">
          <div class="wh-amber-banner">
            <b>{{ t('Signing secret показывается ОДИН раз.') }}</b> {{ t('Используется для HMAC-SHA256 подписи payload\'а. Получатель должен проверять') }} <code>X-UzAssets-Signature: sha256=...</code>.
          </div>
          <div class="wh-token-box">
            <code>{{ plaintextSecret.plaintext_secret }}</code>
            <button class="wh-btn wh-btn-primary" @click="copySecret">
              <BIcon name="copy" :size="14" /> {{ t('Скопировать') }}
            </button>
          </div>
          <div style="font-size: 10.5px; color: var(--color-text-tertiary); margin-top: 8px;">
            Target: <code>{{ plaintextSecret.target_url }}</code> · Events: {{ plaintextSecret.events.length }}
          </div>
        </div>
        <div class="wh-modal-footer">
          <button class="wh-btn wh-btn-primary" @click="plaintextSecret = null">{{ t('Я сохранил — закрыть') }}</button>
        </div>
      </div>
    </div>

    <!-- ───── Modal: delete confirm ───── -->
    <div v-if="deleteTarget" class="wh-modal-bg" @click.self="deleteTarget = null">
      <div class="wh-modal">
        <div class="wh-modal-hd" style="color: #A32D2D;">{{ t('Удалить подписку "') }}{{ deleteTarget.name }}"?</div>
        <div class="wh-modal-body">
          <div style="font-size: 11.5px; color: var(--color-text-secondary);">
            {{ t('История доставок (') }}{{ deleteTarget.total_deliveries }} {{ t('записей) будет удалена каскадно. Действие необратимо.') }}
          </div>
        </div>
        <div class="wh-modal-footer">
          <button class="wh-btn wh-btn-ghost" @click="deleteTarget = null">{{ t('Отмена') }}</button>
          <button class="wh-btn wh-btn-danger" @click="confirmDelete">{{ t('Удалить') }}</button>
        </div>
      </div>
    </div>

    <!-- ───── Modal: delivery detail ───── -->
    <div v-if="showDeliveryDetail" class="wh-modal-bg" @click.self="showDeliveryDetail = null">
      <div class="wh-modal" style="max-width: 740px;">
        <div class="wh-modal-hd">Delivery {{ showDeliveryDetail.id.slice(0, 8) }}</div>
        <div class="wh-modal-body">
          <div class="wh-detail-meta">
            <div><span>Event</span><code>{{ showDeliveryDetail.event_code }}</code></div>
            <div><span>Status</span>
              <span class="wh-pill" :style="{ color: statusPill(showDeliveryDetail.status).color, background: statusPill(showDeliveryDetail.status).bg }">
                {{ t(statusPill(showDeliveryDetail.status).label) }}
              </span>
            </div>
            <div><span>HTTP</span><code>{{ showDeliveryDetail.http_status ?? "—" }}</code></div>
            <div><span>Attempt</span><code>{{ showDeliveryDetail.attempt_number }}</code></div>
            <div><span>Duration</span><code>{{ showDeliveryDetail.duration_ms ?? "—" }}ms</code></div>
            <div><span>Signature</span><code style="font-size: 10px;">{{ showDeliveryDetail.signature || "—" }}</code></div>
            <div><span>Timestamp</span><code>{{ showDeliveryDetail.timestamp_sent || "—" }}</code></div>
            <div v-if="showDeliveryDetail.next_retry_at"><span>Next retry</span><code>{{ fmtDate(showDeliveryDetail.next_retry_at) }}</code></div>
          </div>

          <div class="wh-detail-sec">
            <div class="wh-detail-hd">Payload</div>
            <pre>{{ JSON.stringify(showDeliveryDetail.event_payload, null, 2) }}</pre>
          </div>

          <div v-if="showDeliveryDetail.error_message" class="wh-detail-sec">
            <div class="wh-detail-hd" style="color: #A32D2D;">{{ t('Ошибка') }}</div>
            <pre style="background: rgba(226,75,74,.05); color: #A32D2D;">{{ showDeliveryDetail.error_message }}</pre>
          </div>

          <div v-if="showDeliveryDetail.response_body_snippet" class="wh-detail-sec">
            <div class="wh-detail-hd">{{ t('Ответ (первые 4 KB)') }}</div>
            <pre>{{ showDeliveryDetail.response_body_snippet }}</pre>
          </div>
        </div>
        <div class="wh-modal-footer">
          <button v-if="showDeliveryDetail.status === 'exhausted' || showDeliveryDetail.status === 'failed'"
                  class="wh-btn" @click="replay(showDeliveryDetail); showDeliveryDetail = null">
            <BIcon name="refresh" :size="14" /> Replay
          </button>
          <button class="wh-btn wh-btn-ghost" @click="showDeliveryDetail = null">{{ t('Закрыть') }}</button>
        </div>
      </div>
    </div>

  </div>
</template>

<style scoped>
.wh-wrap { flex: 1; display: flex; flex-direction: column; background: var(--color-background-tertiary); }

.wh-stats {
  display: flex; gap: 8px; align-items: center;
  padding: 12px 18px;
  background: var(--color-background-primary);
  border-bottom: 0.5px solid var(--color-border-tertiary);
}
.wh-stat {
  background: rgba(127,119,221,.05);
  padding: 8px 14px;
  border-radius: 8px;
  min-width: 110px;
}
.wh-stat-l { font-size: 9.5px; color: var(--color-text-tertiary); text-transform: uppercase; letter-spacing: .06em; }
.wh-stat-v { font-size: 18px; color: var(--color-text-primary); font-weight: 400; letter-spacing: -.025em; font-feature-settings: "tnum"; }
.wh-stat-tot { font-size: 12px; color: var(--color-text-tertiary); }
.wh-stat-warn { color: var(--amber); }

.wh-body { display: grid; grid-template-columns: 280px 1fr; flex: 1; min-height: 0; }

.wh-side { background: var(--color-background-primary); border-right: 0.5px solid var(--color-border-tertiary); overflow-y: auto; }
.wh-side-hd { font-size: 9.5px; color: var(--color-text-tertiary); padding: 12px 14px 6px; text-transform: uppercase; letter-spacing: .06em; }
.wh-sub-list { display: flex; flex-direction: column; }
.wh-sub-all, .wh-sub {
  padding: 8px 14px;
  cursor: pointer;
  display: flex; align-items: center; gap: 9px;
  border-bottom: 0.5px solid rgba(0,0,0,.04);
  position: relative; overflow: hidden;
}
.wh-sub-all { font-size: 11.5px; color: var(--color-text-secondary); display: flex; justify-content: space-between; align-items: center; }
.wh-sub-all:hover, .wh-sub:hover { background: rgba(127,119,221,.04); }
.wh-sub-all.active, .wh-sub.active { background: rgba(127,119,221,.08); }
.wh-sub-all.active::before, .wh-sub.active::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 2px; background: #7F77DD;
  animation: uzaStripeDrawIn .4s var(--ease-standard) both;
  transform-origin: left center;
  pointer-events: none;
}
.wh-sub.off { opacity: .55; }
.wh-sub-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.wh-sub-info { flex: 1; min-width: 0; }
.wh-sub-name { font-size: 11.5px; font-weight: 500; color: var(--color-text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wh-sub-url { font-size: 9.5px; color: var(--color-text-tertiary); font-family: var(--font-mono, monospace); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wh-sub-meta { font-size: 9.5px; color: var(--color-text-tertiary); display: flex; gap: 5px; margin-top: 1px; }
.wh-c { background: rgba(0,0,0,.05); padding: 1px 6px; border-radius: 8px; font-size: 9px; }

.wh-main { padding: 14px 18px; overflow-y: auto; }

.wh-sel-hd {
  background: linear-gradient(90deg, rgba(127,119,221,.06), transparent);
  padding: 11px 14px;
  border-radius: 7px;
  display: flex; justify-content: space-between; align-items: flex-start; gap: 12px;
  margin-bottom: 14px;
  position: relative; overflow: hidden;
}
.wh-sel-hd::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; background: #7F77DD;
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  animation:
    uzaStripeDrawIn .8s var(--ease-standard) 100ms both,
    uzaStripeBreathe 2.8s ease-in-out 1s infinite;
  pointer-events: none;
}
.wh-amber-banner {
  background: rgba(239,159,39,.08);
  padding: 9px 12px;
  font-size: 11.5px; color: #854F0B; margin-bottom: 12px;
  border-radius: 5px;
  position: relative; overflow: hidden;
}
.wh-amber-banner::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; background: var(--amber);
  animation: uzaStripeDrawIn .6s var(--ease-standard) both;
  transform-origin: left center;
  pointer-events: none;
}
.wh-sel-name { font-size: 13.5px; font-weight: 500; color: var(--color-text-primary); }
.wh-sel-url { font-size: 11px; color: var(--color-text-secondary); margin-top: 2px; }
.wh-sel-url code { font-family: var(--font-mono, monospace); }
.wh-sel-meta { font-size: 10.5px; color: var(--color-text-tertiary); margin-top: 4px; display: flex; gap: 9px; flex-wrap: wrap; align-items: center; }
.wh-sel-actions { display: flex; gap: 4px; flex-shrink: 0; }

.wh-log-hd { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }
.wh-log-t { font-size: 12px; color: var(--color-text-primary); font-weight: 500; margin-right: auto; }
.wh-filter { padding: 5px 9px; border: 0.5px solid var(--color-border-tertiary); border-radius: 5px; font-size: 11px; font-family: inherit; }

.wh-deliv { width: 100%; border-collapse: collapse; }
.wh-deliv th {
  text-align: left; padding: 7px 10px;
  font-size: 9px; color: var(--color-text-tertiary);
  text-transform: uppercase; letter-spacing: .06em; font-weight: 500;
  background: var(--bg2, #FAFAFC); border-bottom: 0.5px solid var(--color-border-tertiary);
}
.wh-deliv-row { cursor: pointer; }
.wh-deliv-row:hover { background: rgba(127,119,221,.03); }
.wh-deliv-row td { padding: 8px 10px; font-size: 11.5px; border-bottom: 0.5px solid rgba(0,0,0,.04); }
.wh-time { font-size: 11px; }
.wh-evc { font-family: var(--font-mono, monospace); font-size: 10.5px; background: rgba(127,119,221,.08); color: var(--p-deep); padding: 1px 6px; border-radius: 3px; }
.wh-replay-tag { background: rgba(239,159,39,.15); color: #854F0B; padding: 1px 5px; border-radius: 3px; font-size: 9px; margin-left: 5px; font-weight: 500; }
.wh-pill { padding: 2px 7px; border-radius: 4px; font-size: 9.5px; font-weight: 600; }
.wh-num { font-feature-settings: "tnum"; font-size: 11px; }

.wh-icon-btn { background: transparent; border: 0; color: var(--color-text-tertiary); cursor: pointer; font-size: 13px; padding: 4px; }
.wh-icon-btn:hover { color: #7F77DD; }

.wh-btn {
  background: var(--color-background-primary);
  border: 0.5px solid var(--color-border-tertiary);
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 11.5px;
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
  color: var(--color-text-secondary);
  display: inline-flex; align-items: center; gap: 4px;
}
.wh-btn:hover { background: rgba(127,119,221,.05); }
.wh-btn-ghost { background: transparent; }
.wh-btn-primary { background: #7F77DD; color: #fff; border-color: #7F77DD; }
.wh-btn-primary:hover { background: var(--p-deep); }
.wh-btn-danger { background: rgba(226,75,74,.08); color: var(--sev-critical); border-color: rgba(226,75,74,.2); }
.wh-btn-danger:hover { background: var(--sev-high); color: #fff; }

/* Modal common */
.wh-modal-bg { position: fixed; inset: 0; z-index: 1000; background: rgba(15,18,40,.45); -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; padding: 20px; }
.wh-modal {
  background: var(--color-background-primary);
  width: 100%; max-width: 460px;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 24px 64px rgba(15,23,60,.18), 0 8px 24px rgba(15,23,60,.08);
  animation: whIn .35s var(--ease-standard);
}
@keyframes whIn { from { transform: scale(.95) translateY(15px); opacity: 0; } to { transform: scale(1) translateY(0); opacity: 1; } }
.wh-modal-hd { padding: 12px 18px; background: linear-gradient(90deg, rgba(127,119,221,.06), transparent); border-bottom: 0.5px solid var(--color-border-tertiary); font-size: 12px; color: var(--color-text-primary); font-weight: 500; }
.wh-modal-body { padding: 14px 18px; display: flex; flex-direction: column; gap: 10px; max-height: 60dvh; overflow-y: auto; }
.wh-modal-footer { padding: 11px 18px; background: var(--bg2, #FAFAFC); border-top: 0.5px solid var(--color-border-tertiary); display: flex; gap: 6px; justify-content: flex-end; }

.wh-field { display: flex; flex-direction: column; gap: 3px; }
.wh-field label { font-size: 9.5px; color: var(--color-text-tertiary); text-transform: uppercase; letter-spacing: .05em; }
.wh-field input, .wh-field select { padding: 6px 10px; border: 0.5px solid var(--color-border-tertiary); border-radius: 6px; font-size: 12px; font-family: inherit; outline: none; }
.wh-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; }
.wh-check { display: flex; align-items: center; gap: 5px; font-size: 11.5px; color: var(--color-text-secondary); padding: 6px 0; text-transform: none; letter-spacing: 0; }

.wh-evt-tree { border: 0.5px solid var(--color-border-tertiary); border-radius: 7px; max-height: 280px; overflow-y: auto; }
.wh-evt-grp { padding: 8px 11px; border-bottom: 0.5px solid rgba(0,0,0,.04); }
.wh-evt-grp-hd { font-size: 9.5px; color: var(--color-text-tertiary); text-transform: uppercase; letter-spacing: .05em; margin-bottom: 5px; }
.wh-evt-opt { display: flex; align-items: flex-start; gap: 6px; padding: 5px 7px; border-radius: 4px; cursor: pointer; }
.wh-evt-opt:hover { background: rgba(127,119,221,.04); }
.wh-evt-opt.on { background: rgba(127,119,221,.1); }
.wh-evt-opt input { margin-top: 1px; }
.wh-evt-opt code { font-family: var(--font-mono, monospace); font-size: 10.5px; color: var(--color-text-primary); }
.wh-evt-opt.on code { color: var(--p-deep); font-weight: 500; }
.wh-evt-lbl { font-size: 10px; color: var(--color-text-tertiary); margin-top: 1px; }

.wh-token-box { background: #1E2A4A; color: #C9D1E0; padding: 12px; border-radius: 7px; display: flex; align-items: center; gap: 8px; word-break: break-all; }
.wh-token-box code { flex: 1; font-family: var(--font-mono, monospace); font-size: 11px; line-height: 1.5; }

.wh-detail-meta { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-bottom: 12px; }
.wh-detail-meta > div { display: flex; gap: 8px; font-size: 11.5px; padding: 4px 0; }
.wh-detail-meta > div > span { color: var(--color-text-tertiary); min-width: 90px; font-size: 9.5px; text-transform: uppercase; letter-spacing: .05em; padding-top: 2px; }
.wh-detail-meta code { font-family: var(--font-mono, monospace); font-size: 10.5px; color: var(--color-text-primary); }
.wh-detail-sec { margin-bottom: 10px; }
.wh-detail-hd { font-size: 9.5px; color: var(--color-text-tertiary); text-transform: uppercase; letter-spacing: .06em; margin-bottom: 4px; }
.wh-detail-sec pre { background: #1E2A4A; color: #C9D1E0; padding: 10px 12px; border-radius: 6px; font-family: var(--font-mono, monospace); font-size: 10.5px; max-height: 240px; overflow: auto; margin: 0; line-height: 1.5; }
</style>
