<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { mfaApi, type MfaStatus, type TelegramPref } from "@/api/mfa";
import { authApi, type SessionInfo } from "@/api/auth";
import { AxiosError } from "axios";
import { useFormatters } from "@/composables/useFormatters";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();


const fmt = useFormatters();

// ─── State ──────────────────────────────────────────────────────────────

const status = ref<MfaStatus | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);

// Telegram link flow

// Enable 2FA — recovery codes returned ONCE
const showRecoveryCodes = ref(false);
const recoveryCodes = ref<string[]>([]);

// Disable confirmation
const disableModalOpen = ref(false);
const disableCode = ref("");

// Unlink confirmation

// Regenerate recovery codes
const regenModalOpen = ref(false);

// ─── Lifecycle ──────────────────────────────────────────────────────────

onMounted(async () => {
  await refresh();
  await loadSessions();
});

// ─── Активные сессии ──────────────────────────────────────────────────────
const sessions = ref<SessionInfo[]>([]);
const sessionsLoading = ref(false);
const revokingOthers = ref(false);

async function loadSessions() {
  sessionsLoading.value = true;
  try {
    sessions.value = await authApi.listSessions();
  } catch (e) {
    error.value = formatError(e);
  } finally {
    sessionsLoading.value = false;
  }
}

async function revokeOne(id: string) {
  try {
    await authApi.revokeSession(id);
    notice.value = t("Сессия завершена");
    await loadSessions();
  } catch (e) {
    error.value = formatError(e);
  }
}

async function revokeOthers() {
  revokingOthers.value = true;
  try {
    const n = await authApi.revokeOtherSessions();
    notice.value = n > 0 ? t("Завершено сессий: {count}", { count: n }) : t("Других активных сессий нет");
    await loadSessions();
  } catch (e) {
    error.value = formatError(e);
  } finally {
    revokingOthers.value = false;
  }
}

/** Человекочитаемая метка устройства/браузера из user-agent. */
function deviceLabel(ua: string | null): string {
  if (!ua) return t('Неизвестное устройство');
  const os = /Windows/i.test(ua) ? "Windows"
    : /Mac OS X|Macintosh/i.test(ua) ? "macOS"
    : /Android/i.test(ua) ? "Android"
    : /iPhone|iPad|iOS/i.test(ua) ? "iOS"
    : /Linux/i.test(ua) ? "Linux" : "—";
  const br = /Edg\//i.test(ua) ? "Edge"
    : /OPR\/|Opera/i.test(ua) ? "Opera"
    : /Chrome\//i.test(ua) ? "Chrome"
    : /Firefox\//i.test(ua) ? "Firefox"
    : /Safari\//i.test(ua) ? "Safari" : t("браузер");
  return `${br} · ${os}`;
}

const hasOtherSessions = computed(() => sessions.value.some((s) => !s.current));

async function refresh() {
  loading.value = true;
  error.value = null;
  try {
    status.value = await mfaApi.status();
  } catch (e) {
    error.value = formatError(e);
  } finally {
    loading.value = false;
  }
}

function formatError(e: unknown): string {
  if (e instanceof AxiosError) {
    return e.response?.data?.detail ?? e.message;
  }
  return String(e);
}

function flash(msg: string) {
  notice.value = msg;
  setTimeout(() => { if (notice.value === msg) notice.value = null; }, 3500);
}





// ─── 2FA enable / disable ───────────────────────────────────────────────


async function confirmDisable() {
  try {
    await mfaApi.disable(disableCode.value.trim());
    disableModalOpen.value = false;
    disableCode.value = "";
    await refresh();
    flash(t("2FA отключена."));
  } catch (e) {
    error.value = formatError(e);
  }
}

async function confirmRegenerate() {
  try {
    const r = await mfaApi.regenerateRecoveryCodes();
    recoveryCodes.value = r.codes;
    showRecoveryCodes.value = true;
    regenModalOpen.value = false;
    await refresh();
  } catch (e) {
    error.value = formatError(e);
  }
}

function copyRecoveryCodes() {
  const text = recoveryCodes.value.join("\n");
  navigator.clipboard.writeText(text).then(() => flash(t("Скопировано в буфер обмена.")));
}

function dismissRecoveryCodes() {
  showRecoveryCodes.value = false;
  recoveryCodes.value = [];
}

// ─── Test notification ──────────────────────────────────────────────────


// ─── Notification prefs ─────────────────────────────────────────────────



</script>

<template>
  <div class="ss-page">
    <div class="ss-topbar">
      <div class="ss-eyebrow">{{ t('UzAssets · настройки') }}</div>
      <div class="ss-title">{{ t('Безопасность') }}</div>
      <div class="ss-sub">{{ t('Двухфакторная аутентификация и уведомления через Telegram') }}</div>
    </div>

    <div v-if="loading" class="ss-loading">{{ t('Загрузка…') }}</div>

    <transition name="uza-fade">
      <div v-if="notice" class="ss-notice">{{ notice }}</div>
    </transition>
    <transition name="uza-fade">
      <div v-if="error" class="ss-error">
        {{ error }}
        <button class="ss-error-close" @click="error = null">×</button>
      </div>
    </transition>

    <!-- Telegram-привязка, 2FA и TG-уведомления удалены 05.08.2026 вместе с
         интеграцией: канала доставки второго фактора не осталось. -->

    <section class="ss-card">
      <div class="ss-card-head">
        <div class="ss-card-icon">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="2" y="3" width="20" height="14" rx="2" />
            <path d="M8 21h8M12 17v4" />
          </svg>
        </div>
        <div class="ss-card-title">{{ t('Активные сессии') }}</div>
        <button v-if="hasOtherSessions" class="ss-btn-ghost ss-sess-revoke-all"
                :disabled="revokingOthers" @click="revokeOthers">
          {{ revokingOthers ? t('Завершаю…') : t('Завершить остальные') }}
        </button>
      </div>
      <div class="ss-card-body">
        <p class="ss-desc">{{ t('Устройства и браузеры, где выполнен вход. Если видите незнакомую сессию — завершите её.') }}</p>
        <div v-if="sessionsLoading" class="ss-sess-empty">{{ t('Загрузка…') }}</div>
        <div v-else-if="!sessions.length" class="ss-sess-empty">{{ t('Нет активных сессий.') }}</div>
        <ul v-else class="ss-sess-list">
          <li v-for="s in sessions" :key="s.id" class="ss-sess-item" :class="{ 'is-current': s.current }">
            <div class="ss-sess-main">
              <span class="ss-sess-device">{{ t(deviceLabel(s.user_agent)) }}</span>
              <span v-if="s.current" class="ss-sess-badge">{{ t('текущая') }}</span>
            </div>
            <div class="ss-sess-meta">
              <span>{{ s.ip_address || t('IP неизвестен') }}</span>
              <span class="ss-sess-dot">·</span>
              <span>{{ t('вход') }} {{ fmt.fmtDateTime(s.started_at) }}</span>
            </div>
            <button v-if="!s.current" class="ss-sess-kill" :title="t('Завершить сессию')"
                    @click="revokeOne(s.id)">{{ t('Завершить') }}</button>
          </li>
        </ul>
      </div>
    </section>

    <!-- ─── Recovery codes modal ─── -->
    <div v-if="showRecoveryCodes" class="ss-modal-backdrop" @click.self="dismissRecoveryCodes">
      <div class="ss-modal">
        <div class="ss-modal-head">
          <h3>{{ t('Recovery-коды') }}</h3>
          <button class="ss-modal-x" @click="dismissRecoveryCodes">×</button>
        </div>
        <div class="ss-modal-body">
          <p class="ss-warn-strong">
            {{ t('Сохраните эти коды в надёжном месте. Это единственный раз, когда они отображаются. Каждый код можно использовать один раз для входа при потере доступа к Telegram.') }}
          </p>
          <div class="ss-codes-grid">
            <div v-for="code in recoveryCodes" :key="code" class="ss-code">{{ code }}</div>
          </div>
          <div class="ss-modal-actions">
            <button class="ss-btn-ghost" @click="copyRecoveryCodes">{{ t('Скопировать все') }}</button>
            <button class="ss-btn-primary" @click="dismissRecoveryCodes">{{ t('Я сохранил, закрыть') }}</button>
          </div>
        </div>
      </div>
    </div>

    <!-- ─── Disable 2FA modal ─── -->
    <div v-if="disableModalOpen" class="ss-modal-backdrop" @click.self="disableModalOpen = false">
      <div class="ss-modal ss-modal-narrow">
        <div class="ss-modal-head">
          <h3>{{ t('Отключить 2FA') }}</h3>
          <button class="ss-modal-x" @click="disableModalOpen = false">×</button>
        </div>
        <div class="ss-modal-body">
          <p>{{ t('Для отключения введите один из ваших recovery-кодов:') }}</p>
          <input
            v-model="disableCode"
            type="text"
            placeholder="XXXX-XXXX"
            class="ss-input ss-input-mono"
          />
          <div class="ss-modal-actions">
            <button class="ss-btn-ghost" @click="disableModalOpen = false">{{ t('Отмена') }}</button>
            <button
              class="ss-btn-danger"
              :disabled="disableCode.trim().length < 8"
              @click="confirmDisable"
            >
              {{ t('Отключить') }}
            </button>
          </div>
        </div>
      </div>
    </div>


    <!-- ─── Regenerate recovery codes modal ─── -->
    <div v-if="regenModalOpen" class="ss-modal-backdrop" @click.self="regenModalOpen = false">
      <div class="ss-modal ss-modal-narrow">
        <div class="ss-modal-head">
          <h3>{{ t('Сгенерировать новые recovery-коды') }}</h3>
          <button class="ss-modal-x" @click="regenModalOpen = false">×</button>
        </div>
        <div class="ss-modal-body">
          <p>
            {{ t('Текущие 10 кодов будут') }} <strong>{{ t('немедленно') }}</strong> {{ t('заменены новыми. После закрытия экрана с новыми кодами они больше не отобразятся.') }}
          </p>
          <div class="ss-modal-actions">
            <button class="ss-btn-ghost" @click="regenModalOpen = false">{{ t('Отмена') }}</button>
            <button class="ss-btn-primary" @click="confirmRegenerate">{{ t('Сгенерировать') }}</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ss-page {
  max-width: 760px;
  margin: 0 auto;
  padding: 24px 28px 80px;
}
.ss-topbar { margin-bottom: 28px; padding-bottom: 18px; border-bottom: 1px solid rgba(15, 23, 60, 0.08); }
.ss-eyebrow { font-size: 10px; font-weight: 500; letter-spacing: 0.08em; text-transform: uppercase; color: var(--t3, var(--t3)); }
.ss-title { font-size: 22px; font-weight: 500; letter-spacing: -0.025em; color: var(--t1, #0F172A); margin-top: 4px; }
.ss-sub { font-size: 13px; font-weight: 400; color: var(--t3, var(--t3)); margin-top: 4px; }

.ss-loading { padding: 40px; text-align: center; color: var(--t3, var(--t3)); font-size: 14px; }

.ss-notice, .ss-error {
  padding: 12px 16px; border-radius: 11px; font-size: 13px; font-weight: 400;
  margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center;
}
.ss-notice { background: rgba(29, 158, 117, 0.10); border: 1px solid rgba(29, 158, 117, 0.25); color: #14724E; }
.ss-error  { background: rgba(239, 68, 68, 0.10); border: 1px solid rgba(239, 68, 68, 0.25); color: #B91C1C; }
.ss-error-close { background: none; border: none; color: inherit; font-size: 18px; cursor: pointer; padding: 0 4px; }

.ss-card {
  background: var(--bg1, #fff); border: 1px solid rgba(15, 23, 60, 0.08); border-radius: 14px;
  margin-bottom: 16px; overflow: hidden;
  box-shadow: 0 2px 6px rgba(15, 23, 60, 0.04);
}
.ss-card-head {
  display: flex; align-items: center; gap: 12px;
  padding: 18px 22px;
  border-bottom: 1px solid rgba(15, 23, 60, 0.06);
}
.ss-card-icon { color: #7F77DD; display: flex; }
.ss-card-title { font-size: 15px; font-weight: 500; letter-spacing: -0.01em; color: var(--t1, #0F172A); flex: 1; }
.ss-card-pill {
  font-size: 10px; font-weight: 500; letter-spacing: 0.06em; text-transform: uppercase;
  padding: 4px 10px; border-radius: 11px;
}
.pill-green { background: rgba(29, 158, 117, 0.12); color: #14724E; }
.pill-grey  { background: rgba(100, 116, 139, 0.12); color: var(--t2, #475569); }

.ss-card-body { padding: 20px 22px; display: flex; flex-direction: column; gap: 12px; }
.ss-desc { font-size: 13px; font-weight: 400; color: var(--t2, #475569); margin: 0; line-height: 1.55; }
.ss-warn { font-size: 12px; color: #B45309; margin: 0; }
.ss-warn-strong { font-size: 13px; color: #B45309; background: rgba(239, 159, 39, 0.10); padding: 10px 14px; border-radius: 10px; border: 1px solid rgba(239, 159, 39, 0.25); margin: 0; line-height: 1.5; }

.ss-info-row { display: flex; gap: 12px; font-size: 13px; }
.ss-label { color: var(--t3, var(--t3)); font-weight: 500; min-width: 110px; }
.ss-value { color: var(--t1, #0F172A); font-weight: 400; }

.ss-actions { display: flex; gap: 10px; margin-top: 8px; }

.ss-btn-primary, .ss-btn-ghost, .ss-btn-danger {
  height: 38px; border-radius: 11px; padding: 0 16px;
  font-size: 13px; font-weight: 500; letter-spacing: 0.01em;
  border: none; cursor: pointer;
  transition: all 0.18s var(--ease-standard);
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
}
.ss-btn-primary { background: #7F77DD; color: #fff; }
.ss-btn-primary:hover:not(:disabled) { background: #6C5CE7; transform: translateY(-1px); }
.ss-btn-primary:disabled { opacity: 0.45; cursor: not-allowed; }

.ss-btn-ghost { background: rgba(127, 119, 221, 0.08); color: #5B53C2; }
.ss-btn-ghost:hover:not(:disabled) { background: rgba(127, 119, 221, 0.14); }
.ss-btn-ghost:disabled { opacity: 0.45; cursor: not-allowed; }

.ss-btn-danger { background: rgba(239, 68, 68, 0.08); color: #B91C1C; }
.ss-btn-danger:hover:not(:disabled) { background: rgba(239, 68, 68, 0.16); }
.ss-btn-danger:disabled { opacity: 0.45; cursor: not-allowed; }

.ss-deep-link {
  display: block;
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-size: 12px;
  padding: 10px 14px;
  background: rgba(127, 119, 221, 0.06);
  border: 1px solid rgba(127, 119, 221, 0.18);
  border-radius: 10px;
  word-break: break-all;
  color: #5B53C2;
  text-decoration: none;
}
.ss-deep-link:hover { background: rgba(127, 119, 221, 0.10); }
.ss-link-meta { font-size: 12px; color: var(--t3, var(--t3)); }

.ss-toggle-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 0;
}
.ss-toggle-row-thin { padding: 8px 0; }
.ss-toggle-name { font-size: 13px; font-weight: 500; color: var(--t1, #0F172A); }
.ss-toggle-hint { font-size: 11px; color: var(--t3, #94A3B8); margin-top: 2px; }
.ss-divider { height: 1px; background: rgba(15, 23, 60, 0.06); margin: 4px 0; }

.ss-switch { position: relative; display: inline-block; width: 42px; height: 24px; flex-shrink: 0; }
.ss-switch input { opacity: 0; width: 0; height: 0; }
.ss-switch-track { position: absolute; cursor: pointer; inset: 0; background: #CBD5E1; transition: 0.18s; border-radius: 24px; }
.ss-switch-track::before {
  content: ""; position: absolute; height: 18px; width: 18px; left: 3px; bottom: 3px;
  background: white; transition: 0.18s; border-radius: 50%;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
}
.ss-switch input:checked + .ss-switch-track { background: #7F77DD; }
.ss-switch input:checked + .ss-switch-track::before { transform: translateX(18px); }
.ss-switch input:disabled + .ss-switch-track { opacity: 0.4; cursor: not-allowed; }

.ss-quiet-times { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 4px; }
.ss-input {
  width: 100%; height: 38px; padding: 0 12px;
  border-radius: 10px; border: 1px solid rgba(15, 23, 60, 0.12);
  background: var(--bg1, #fff); font-size: 13px; transition: all 0.15s;
}
.ss-input:focus { outline: none; border-color: #7F77DD; box-shadow: 0 0 0 3px rgba(127, 119, 221, 0.18); }
.ss-input:disabled { opacity: 0.55; }
.ss-input-mono { font-family: ui-monospace, "SF Mono", Menlo, monospace; letter-spacing: 0.08em; text-transform: uppercase; text-align: center; }

/* ─── Modals ──────────────────────────────────────────────────────────── */
.ss-modal-backdrop {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(15, 18, 40, 0.45);
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center;
  padding: 20px;
  animation: bgIn .25s;
}
@keyframes bgIn { from { opacity: 0; } to { opacity: 1; } }
.ss-modal {
  background: var(--bg1, #fff); border-radius: 14px; max-width: 560px; width: 100%;
  box-shadow: 0 24px 64px rgba(15, 23, 60, 0.18), 0 8px 24px rgba(15, 23, 60, 0.08);
  animation: modalIn .45s var(--ease-standard);
}
.ss-modal-narrow { max-width: 420px; }
@keyframes modalIn {
  from { opacity: 0; transform: translateY(20px) scale(0.97); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}
.ss-modal-head {
  padding: 18px 22px; display: flex; align-items: center; justify-content: space-between;
  border-bottom: 1px solid rgba(15, 23, 60, 0.06);
}
.ss-modal-head h3 { font-size: 15px; font-weight: 500; letter-spacing: -0.01em; color: var(--t1, #0F172A); margin: 0; }
.ss-modal-x { background: none; border: none; font-size: 22px; cursor: pointer; color: var(--t3, #94A3B8); padding: 0 4px; }
.ss-modal-x:hover { color: var(--t1, #0F172A); }
.ss-modal-body { padding: 20px 22px; display: flex; flex-direction: column; gap: 14px; font-size: 13px; color: var(--t2, #334155); line-height: 1.55; }
.ss-modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 8px; }

.ss-codes-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 8px;
  padding: 14px; background: var(--bg2, #F8FAFC); border-radius: 10px;
  border: 1px solid rgba(15, 23, 60, 0.06);
}
.ss-code {
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-size: 13px; padding: 6px 10px; background: var(--bg1, #fff);
  border-radius: 8px; text-align: center; letter-spacing: 0.08em;
  color: var(--t1, #0F172A); border: 1px solid rgba(15, 23, 60, 0.06);
}

.uza-fade-enter-active, .uza-fade-leave-active { transition: opacity 0.2s; }
.uza-fade-enter-from, .uza-fade-leave-to { opacity: 0; }

/* ─── Активные сессии ─── */
.ss-sess-revoke-all { margin-left: auto; font-size: 12.5px; padding: 6px 12px; }
.ss-sess-empty { font-size: 13px; color: var(--t3, #94a3b8); padding: 8px 2px; }
.ss-sess-list { list-style: none; margin: 10px 0 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.ss-sess-item {
  display: grid;
  grid-template-columns: 1fr auto;
  grid-template-areas: "main kill" "meta kill";
  align-items: center;
  gap: 2px 12px;
  padding: 11px 14px;
  border: 1px solid rgba(15, 23, 60, 0.08);
  border-radius: 12px;
  background: #fff;
}
.ss-sess-item.is-current { border-color: rgba(30, 181, 58, 0.35); background: rgba(30, 181, 58, 0.05); }
.ss-sess-main { grid-area: main; display: flex; align-items: center; gap: 8px; }
.ss-sess-device { font-size: 13.5px; font-weight: 600; color: var(--t1, #1E2A4A); }
.ss-sess-badge {
  font-size: 10.5px; font-weight: 700; color: #1D9E75;
  background: rgba(30, 181, 58, 0.12); border-radius: 999px; padding: 2px 8px;
}
.ss-sess-meta { grid-area: meta; display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--t3, #94a3b8); font-variant-numeric: tabular-nums; }
.ss-sess-dot { opacity: 0.5; }
.ss-sess-kill {
  grid-area: kill; align-self: center;
  font-size: 12.5px; font-weight: 600; color: #E24B4A;
  background: rgba(226, 75, 74, 0.08); border: none; border-radius: 9px;
  padding: 7px 13px; cursor: pointer; transition: background 0.15s;
}
.ss-sess-kill:hover { background: rgba(226, 75, 74, 0.16); }
</style>
