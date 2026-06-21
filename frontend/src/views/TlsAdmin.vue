<script setup lang="ts">
/**
 * TlsAdmin — admin UI for TLS certificate management (Pack 150).
 *
 * 4 секции:
 *  1. Текущий сертификат — issuer, domain, expiry, days left progress bar
 *  2. Let's Encrypt — domain + email + staging-checkbox + run button
 *  3. Manual upload — 2 textareas (cert + key) или file pickers
 *  4. Квартальный auto-renewal — toggle + interval setting
 *
 * Все операции audit_log; install/renew = is_critical.
 */
import { computed, onMounted, ref } from "vue";
import { tlsApi, formatDaysLeft, shortDate } from "@/api/tlsAdmin";
import type { CertStatus, InstallResult } from "@/api/tlsAdmin";
import { useToast } from "@/composables/useToast";
import { useConfirm } from "@/composables/useConfirm";

const toast = useToast();
const { confirmDialog } = useConfirm();

const status = ref<CertStatus | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);

const daysLeftFmt = computed(() => formatDaysLeft(status.value?.info?.days_left));
const expiryBarPct = computed(() => {
  const d = status.value?.info?.days_left ?? 0;
  return Math.min(100, Math.max(0, (d / 90) * 100));
});

async function load() {
  loading.value = true;
  error.value = null;
  try {
    status.value = await tlsApi.status();
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Ошибка загрузки";
  } finally {
    loading.value = false;
  }
}

// ────── Let's Encrypt
const leDomain = ref("");
const leEmail = ref("");
const leStaging = ref(false);
const leBusy = ref(false);
const leResult = ref<InstallResult | string | null>(null);

async function runLe() {
  if (!leDomain.value || !leEmail.value) return;
  if (!(await confirmDialog({ message: `Выпустить сертификат для ${leDomain.value}?\n\nЭто перепишет текущий cert.`, danger: true }))) return;
  leBusy.value = true;
  leResult.value = null;
  try {
    leResult.value = await tlsApi.letsEncrypt(leDomain.value.trim(), leEmail.value.trim(), leStaging.value);
    await load();
  } catch (e: any) {
    leResult.value = e?.response?.data?.detail || e?.message || "Ошибка LE";
  } finally {
    leBusy.value = false;
  }
}

// ────── Manual upload
const certPem = ref("");
const keyPem = ref("");
const uploadBusy = ref(false);
const uploadResult = ref<InstallResult | string | null>(null);

async function uploadCert() {
  if (!certPem.value.trim() || !keyPem.value.trim()) return;
  if (!(await confirmDialog({ message: "Установить новый сертификат? Текущий будет забэкаплен.", danger: true }))) return;
  uploadBusy.value = true;
  uploadResult.value = null;
  try {
    uploadResult.value = await tlsApi.upload(certPem.value, keyPem.value);
    certPem.value = "";
    keyPem.value = "";
    await load();
  } catch (e: any) {
    uploadResult.value = e?.response?.data?.detail || e?.message || "Ошибка upload";
  } finally {
    uploadBusy.value = false;
  }
}

function onFile(field: "cert" | "key", e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0];
  if (!file) return;
  const r = new FileReader();
  r.onload = () => {
    const txt = String(r.result || "");
    if (field === "cert") certPem.value = txt;
    else keyPem.value = txt;
  };
  r.readAsText(file);
}

// ────── Schedule
const scheduleBusy = ref(false);
const scheduleEnabled = ref(false);
const scheduleInterval = ref(90);

async function saveSchedule() {
  scheduleBusy.value = true;
  try {
    await tlsApi.updateSchedule(scheduleEnabled.value, scheduleInterval.value);
    await load();
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || e?.message || "Ошибка сохранения расписания");
  } finally {
    scheduleBusy.value = false;
  }
}

function syncScheduleFromStatus() {
  if (status.value?.config) {
    scheduleEnabled.value = status.value.config.schedule_enabled;
    scheduleInterval.value = status.value.config.schedule_interval_days || 90;
  }
}

function formatResult(r: InstallResult | string | null): string {
  if (!r) return "";
  if (typeof r === "string") return r;
  if (r.ok) {
    return `✓ Установлено: ${r.info?.subject || "новый cert"} · истекает ${shortDate(r.info?.not_after)}`;
  }
  return "Не удалось установить";
}

onMounted(async () => {
  await load();
  syncScheduleFromStatus();
});
</script>

<template>
  <div class="tls-page">
    <!-- Header -->
    <div class="tls-header">
      <div class="tls-eyebrow">ADMIN · INFRASTRUCTURE</div>
      <h1 class="tls-title">TLS-сертификат</h1>
      <div class="tls-sub">
        HTTPS-сертификат для <code>{{ status?.config?.domain || "domain (не задан)" }}</code> ·
        управление через Let's Encrypt или ручную загрузку
      </div>
    </div>

    <div v-if="error" class="tls-error">{{ error }}</div>
    <div v-else-if="loading && !status" class="tls-loading">Загрузка…</div>

    <template v-else-if="status">
      <!-- ────── Текущий сертификат ────── -->
      <section class="tls-card">
        <div class="tls-card-head">
          <h2>Текущий сертификат</h2>
          <span class="tls-tag" :class="`tls-tag-${status.active_label === 'production' ? 'ok' : 'warn'}`">
            {{ status.active_label === "production" ? "PRODUCTION" : status.active_label === "dev-fallback" ? "DEV FALLBACK" : "НЕТ" }}
          </span>
          <button class="tls-btn-icon" @click="load" title="Обновить" aria-label="Обновить">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
          </button>
        </div>
        <div class="tls-grid">
          <div class="tls-field">
            <div class="tls-field-label">Домен (CN/SAN)</div>
            <div class="tls-field-value tls-mono">{{ status.info?.san?.[0] || status.info?.subject || "—" }}</div>
          </div>
          <div class="tls-field">
            <div class="tls-field-label">Издатель</div>
            <div class="tls-field-value tls-mono tls-issuer">{{ status.info?.issuer || "—" }}</div>
          </div>
          <div class="tls-field">
            <div class="tls-field-label">Действителен с</div>
            <div class="tls-field-value">{{ shortDate(status.info?.not_before) }}</div>
          </div>
          <div class="tls-field">
            <div class="tls-field-label">Истекает</div>
            <div class="tls-field-value">
              {{ shortDate(status.info?.not_after) }}
              <span class="tls-pill" :class="`tls-pill-${daysLeftFmt.tone}`">{{ daysLeftFmt.text }}</span>
            </div>
          </div>
          <div class="tls-field tls-field-full">
            <div class="tls-field-label">Срок жизни</div>
            <div class="tls-bar">
              <div class="tls-bar-fill" :class="`tls-bar-${daysLeftFmt.tone}`" :style="{ width: `${expiryBarPct}%` }"></div>
            </div>
          </div>
          <div class="tls-field" v-if="status.info?.san?.length">
            <div class="tls-field-label">SAN</div>
            <div class="tls-field-value tls-mono">{{ status.info.san.join(", ") }}</div>
          </div>
          <div class="tls-field">
            <div class="tls-field-label">Источник</div>
            <div class="tls-field-value">
              {{ status.config?.source === "letsencrypt" ? "Let's Encrypt" : status.config?.source === "manual" ? "Ручная загрузка" : "—" }}
              <span v-if="status.config?.renewed_at" class="tls-meta">
                · обновлён {{ shortDate(status.config.renewed_at) }}
              </span>
            </div>
          </div>
        </div>
      </section>

      <!-- ────── Let's Encrypt ────── -->
      <section class="tls-card">
        <div class="tls-card-head">
          <h2>Let's Encrypt</h2>
          <span class="tls-meta">бесплатный выпуск через ACME HTTP-01</span>
        </div>
        <div class="tls-form">
          <div class="tls-form-row">
            <label class="tls-label">Домен
              <input v-model="leDomain" type="text" placeholder="platform.uz-assets.uz" class="tls-input tls-mono"/>
            </label>
            <label class="tls-label">Email
              <input v-model="leEmail" type="email" placeholder="admin@uz-assets.uz" class="tls-input"/>
            </label>
          </div>
          <label class="tls-check">
            <input v-model="leStaging" type="checkbox"/>
            <span>Staging environment (для тестов — выдаёт untrusted cert; production limit 5 issuances/week)</span>
          </label>
          <div class="tls-actions">
            <button class="tls-btn tls-btn-primary" :disabled="leBusy || !leDomain || !leEmail" @click="runLe">
              {{ leBusy ? "Выпуск…" : "Выпустить" }}
            </button>
            <div v-if="leResult" class="tls-result" :class="{ 'is-err': typeof leResult === 'string' || !(leResult as any).ok }">
              {{ formatResult(leResult) }}
            </div>
          </div>
          <div class="tls-hint">
            <strong>Условие:</strong> домен должен указывать на IP nginx-app, порт 80 открыт наружу.
            certbot валидирует через <code>/.well-known/acme-challenge/</code>.
            После успеха — выполните <code>docker exec uza-nginx nginx -s reload</code>.
          </div>
        </div>
      </section>

      <!-- ────── Manual upload ────── -->
      <section class="tls-card">
        <div class="tls-card-head">
          <h2>Ручная загрузка</h2>
          <span class="tls-meta">PEM из любого источника (uzcloud LE, корпоративный CA, paid cert)</span>
        </div>
        <div class="tls-form">
          <div class="tls-form-row">
            <label class="tls-label">
              <span>Сертификат (fullchain.pem)</span>
              <input type="file" accept=".pem,.crt,.cer,.txt" @change="onFile('cert', $event)" class="tls-file"/>
              <textarea v-model="certPem" rows="6" placeholder="-----BEGIN CERTIFICATE-----&#10;...&#10;-----END CERTIFICATE-----" class="tls-textarea tls-mono"/>
            </label>
            <label class="tls-label">
              <span>Приватный ключ (privkey.pem)</span>
              <input type="file" accept=".pem,.key,.txt" @change="onFile('key', $event)" class="tls-file"/>
              <textarea v-model="keyPem" rows="6" placeholder="-----BEGIN PRIVATE KEY-----&#10;...&#10;-----END PRIVATE KEY-----" class="tls-textarea tls-mono"/>
            </label>
          </div>
          <div class="tls-actions">
            <button class="tls-btn tls-btn-primary" :disabled="uploadBusy || !certPem || !keyPem" @click="uploadCert">
              {{ uploadBusy ? "Установка…" : "Установить" }}
            </button>
            <div v-if="uploadResult" class="tls-result" :class="{ 'is-err': typeof uploadResult === 'string' || !(uploadResult as any).ok }">
              {{ formatResult(uploadResult) }}
            </div>
          </div>
          <div class="tls-hint">
            <strong>Замечание:</strong> валидация PEM-формата на сервере (cryptography lib).
            Текущий cert будет забэкаплен в <code>certs/backups/</code>.
            После установки выполните <code>docker exec uza-nginx nginx -s reload</code>.
          </div>
        </div>
      </section>

      <!-- ────── Schedule ────── -->
      <section class="tls-card">
        <div class="tls-card-head">
          <h2>Автоматическое обновление</h2>
          <span class="tls-meta">Background-job проверяет раз в 24h</span>
        </div>
        <div class="tls-form">
          <label class="tls-check tls-check-big">
            <input v-model="scheduleEnabled" type="checkbox"/>
            <span>Включить автоматический renewal через Let's Encrypt</span>
          </label>
          <div class="tls-form-row" v-if="scheduleEnabled">
            <label class="tls-label">Интервал
              <select v-model.number="scheduleInterval" class="tls-input">
                <option :value="60">60 дней</option>
                <option :value="90">90 дней (квартал) — рекомендуется</option>
                <option :value="120">120 дней</option>
                <option :value="180">180 дней (полгода)</option>
              </select>
            </label>
            <div class="tls-label">
              <span>Условия запуска</span>
              <div class="tls-cond-list">
                <div>• С предыдущего renewal прошло ≥ выбранного интервала</div>
                <div>• ИЛИ до expiry осталось &lt; 30 дней</div>
                <div>• Домен/email берутся из последнего успешного LE</div>
              </div>
            </div>
          </div>
          <div class="tls-actions">
            <button class="tls-btn tls-btn-primary" :disabled="scheduleBusy" @click="saveSchedule">
              {{ scheduleBusy ? "Сохранение…" : "Сохранить" }}
            </button>
          </div>
          <div v-if="status.config?.last_le_attempt" class="tls-hint">
            <strong>Последняя попытка:</strong> {{ shortDate(status.config.last_le_attempt) }}
            <span v-if="status.config.last_le_result?.code === 0" class="tls-pill tls-pill-ok">УСПЕХ</span>
            <span v-else-if="status.config.last_le_result?.code !== undefined" class="tls-pill tls-pill-crit">
              EXIT {{ status.config.last_le_result.code }}
            </span>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.tls-page {
  padding: 16px 22px 28px;
  font-family: var(--font, system-ui);
  background: #F4F3F9;
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.tls-header {
  background: var(--bg1, #fff);
  border-radius: 14px;
  padding: 18px 22px;
  box-shadow: 0 1px 0 rgba(15, 23, 60, 0.06), 0 12px 32px rgba(15, 23, 60, 0.06);
}
.tls-eyebrow {
  font-size: 9.5px; font-weight: 600; letter-spacing: 0.09em;
  text-transform: uppercase; color: var(--t3, var(--t-muted));
}
.tls-title {
  font-size: 22px; font-weight: 500; color: var(--t1, #1E2A4A);
  letter-spacing: -0.015em; margin: 4px 0;
}
.tls-sub { font-size: 12px; color: var(--t3, var(--t-muted)); }
.tls-sub code { background: #F4F3F9; padding: 1px 6px; border-radius: 4px; font-size: 11.5px; }

.tls-card {
  background: var(--bg1, #fff);
  border-radius: 14px;
  padding: 18px 22px;
  box-shadow: 0 1px 0 rgba(15, 23, 60, 0.06), 0 12px 32px rgba(15, 23, 60, 0.06);
}
.tls-card-head {
  display: flex; align-items: center; gap: 12px;
  padding-bottom: 14px; margin-bottom: 14px;
  border-bottom: 1px solid #EFEEF4;
}
.tls-card-head h2 {
  margin: 0; font-size: 15px; font-weight: 500; color: var(--t1, #1E2A4A);
}
.tls-meta { font-size: 11.5px; color: var(--t3, var(--t-muted)); margin-left: auto; }

.tls-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px 24px;
}
.tls-field-full { grid-column: 1 / -1; }
.tls-field-label {
  font-size: 10px; font-weight: 600; letter-spacing: 0.06em;
  text-transform: uppercase; color: var(--t3, var(--t-muted)); margin-bottom: 4px;
}
.tls-field-value {
  font-size: 13px; color: var(--t1, #1E2A4A);
  display: flex; gap: 8px; align-items: center;
}
.tls-mono { font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 12px; }
.tls-issuer { font-size: 11px; color: #51596F; }

.tls-bar {
  height: 8px; background: #EFEEF4; border-radius: 6px; overflow: hidden;
}
.tls-bar-fill {
  height: 100%; border-radius: 6px;
  transition: width 0.4s var(--ease-standard);
}
.tls-bar-ok   { background: linear-gradient(90deg, var(--green), #2BCD8A); }
.tls-bar-warn { background: linear-gradient(90deg, var(--amber), #FFC370); }
.tls-bar-crit { background: linear-gradient(90deg, #C53737, var(--sev-high)); }

.tls-pill {
  font-size: 9px; font-weight: 600;
  padding: 3px 8px; border-radius: 11px;
  background: #EFEEF4; color: #51596F;
  letter-spacing: 0.04em;
}
.tls-pill-ok   { background: rgba(29, 158, 117, 0.15); color: #157A56; }
.tls-pill-warn { background: rgba(239, 159, 39, 0.18); color: #A06B0C; }
.tls-pill-crit { background: rgba(226, 75, 74, 0.15); color: #C36868; }

.tls-tag {
  font-size: 9px; font-weight: 700;
  padding: 4px 10px; border-radius: 11px;
  letter-spacing: 0.08em;
}
.tls-tag-ok   { background: rgba(29, 158, 117, 0.15); color: #157A56; }
.tls-tag-warn { background: rgba(239, 159, 39, 0.18); color: #A06B0C; }

.tls-btn-icon {
  background: none; border: none; cursor: pointer;
  font-size: 14px; color: var(--t3, var(--t-muted)); padding: 4px 8px;
  border-radius: 6px; transition: background 0.15s;
  font-family: inherit;
}
.tls-btn-icon:hover { background: var(--bg2, #FAFAFC); color: var(--p-deep); }

.tls-form {
  display: flex; flex-direction: column; gap: 12px;
}
.tls-form-row {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
}
.tls-label {
  display: flex; flex-direction: column; gap: 6px;
  font-size: 11.5px; color: #51596F; font-weight: 500;
}
.tls-input, .tls-textarea {
  font-family: inherit;
  font-size: 12.5px;
  padding: 8px 12px;
  border: 1px solid #E5E5EA;
  border-radius: 8px;
  outline: none;
  background: var(--bg1, #fff);
  color: var(--t1, #1E2A4A);
  width: 100%;
  box-sizing: border-box;
}
.tls-input:focus, .tls-textarea:focus { border-color: #7F77DD; }
.tls-textarea {
  resize: vertical;
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-size: 11px;
  background: var(--bg2, #FAFAFC);
}
.tls-file {
  font-family: inherit; font-size: 11px; color: var(--t3, var(--t-muted));
}
.tls-check {
  display: flex; gap: 8px; align-items: flex-start;
  font-size: 12px; color: #51596F;
  cursor: pointer;
}
.tls-check input { margin-top: 2px; }
.tls-check-big { font-size: 13px; color: var(--t1, #1E2A4A); }

.tls-actions {
  display: flex; gap: 12px; align-items: center;
}
.tls-btn {
  background: var(--bg1, #fff); color: var(--t1, #1E2A4A);
  border: 1px solid #E5E5EA; border-radius: 7px;
  font-size: 12px; font-weight: 500;
  padding: 8px 18px; cursor: pointer;
  font-family: inherit;
  transition: all 0.15s;
}
.tls-btn:hover { background: var(--bg2, #FAFAFC); border-color: #D5D5DA; }
.tls-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.tls-btn-primary {
  background: #7F77DD; color: #fff; border-color: #7F77DD;
}
.tls-btn-primary:hover { background: var(--p-deep); border-color: var(--p-deep); }

.tls-result {
  font-size: 12px; color: #157A56;
  padding: 6px 12px; background: rgba(29, 158, 117, 0.08);
  border-radius: 6px; border: 1px solid rgba(29, 158, 117, 0.18);
}
.tls-result.is-err {
  color: #C36868;
  background: rgba(226, 75, 74, 0.08);
  border-color: rgba(226, 75, 74, 0.2);
}

.tls-hint {
  font-size: 11.5px; color: var(--t3, var(--t-muted));
  padding: 10px 14px; background: var(--bg2, #FAFAFC); border-radius: 8px;
  line-height: 1.6;
}
.tls-hint code {
  background: var(--bg1, #fff); padding: 1px 6px; border-radius: 4px;
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-size: 11px; color: var(--p-deep);
}
.tls-hint strong { color: var(--t1, #1E2A4A); }
.tls-cond-list {
  font-size: 11.5px; color: var(--t3, var(--t-muted));
  line-height: 1.7;
  padding-top: 4px;
}

.tls-error {
  padding: 16px;
  background: rgba(226, 75, 74, 0.08);
  border: 1px solid rgba(226, 75, 74, 0.25);
  border-radius: 8px;
  color: #C36868;
  font-size: 12.5px;
}
.tls-loading {
  padding: 40px; text-align: center; color: var(--t3, var(--t-muted)); font-size: 13px;
}
</style>
