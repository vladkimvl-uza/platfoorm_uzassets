<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { mfaApi, type MfaStatus, type TelegramPref } from "@/api/mfa";
import { AxiosError } from "axios";
import { useFormatters } from "@/composables/useFormatters";

const fmt = useFormatters();

// ─── State ──────────────────────────────────────────────────────────────

const status = ref<MfaStatus | null>(null);
const prefs = ref<TelegramPref | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);

// Telegram link flow
const linkDeepLink = ref<string | null>(null);
const linkToken = ref<string | null>(null);
const linkExpiresAt = ref<string | null>(null);
const linkPolling = ref(false);
let pollTimer: number | null = null;

// Enable 2FA — recovery codes returned ONCE
const showRecoveryCodes = ref(false);
const recoveryCodes = ref<string[]>([]);

// Disable confirmation
const disableModalOpen = ref(false);
const disableCode = ref("");

// Unlink confirmation
const unlinkModalOpen = ref(false);

// Regenerate recovery codes
const regenModalOpen = ref(false);

// ─── Lifecycle ──────────────────────────────────────────────────────────

onMounted(async () => {
  await refresh();
});

async function refresh() {
  loading.value = true;
  error.value = null;
  try {
    status.value = await mfaApi.status();
    prefs.value = await mfaApi.getPrefs();
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

// ─── Telegram link flow ─────────────────────────────────────────────────

async function startLink() {
  try {
    const r = await mfaApi.linkTelegram();
    linkDeepLink.value = r.deep_link;
    linkToken.value = r.token;
    linkExpiresAt.value = r.expires_at;
    // Poll status every 3s for up to 5 min — auto-detect when bot confirms
    linkPolling.value = true;
    let elapsed = 0;
    pollTimer = window.setInterval(async () => {
      elapsed += 3;
      try {
        const s = await mfaApi.status();
        if (s.telegram_linked) {
          status.value = s;
          linkPolling.value = false;
          linkDeepLink.value = null;
          linkToken.value = null;
          if (pollTimer) clearInterval(pollTimer);
          flash("Telegram успешно привязан.");
        } else if (elapsed >= 300) {
          linkPolling.value = false;
          if (pollTimer) clearInterval(pollTimer);
        }
      } catch {
        // ignore
      }
    }, 3000);
  } catch (e) {
    error.value = formatError(e);
  }
}

function cancelLink() {
  linkDeepLink.value = null;
  linkToken.value = null;
  linkPolling.value = false;
  if (pollTimer) clearInterval(pollTimer);
}

async function confirmUnlink() {
  try {
    await mfaApi.unlinkTelegram();
    unlinkModalOpen.value = false;
    await refresh();
    flash("Telegram отвязан.");
  } catch (e) {
    error.value = formatError(e);
  }
}

// ─── 2FA enable / disable ───────────────────────────────────────────────

async function enable2fa() {
  try {
    const r = await mfaApi.enable("telegram");
    recoveryCodes.value = r.recovery_codes;
    showRecoveryCodes.value = true;
    await refresh();
  } catch (e) {
    error.value = formatError(e);
  }
}

async function confirmDisable() {
  try {
    await mfaApi.disable(disableCode.value.trim());
    disableModalOpen.value = false;
    disableCode.value = "";
    await refresh();
    flash("2FA отключена.");
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
  navigator.clipboard.writeText(text).then(() => flash("Скопировано в буфер обмена."));
}

function dismissRecoveryCodes() {
  showRecoveryCodes.value = false;
  recoveryCodes.value = [];
}

// ─── Test notification ──────────────────────────────────────────────────

const testSending = ref(false);
async function sendTest() {
  testSending.value = true;
  try {
    const r = await mfaApi.testNotification();
    if (r.enqueued) {
      flash("Тест отправлен. Сообщение придёт в Telegram через несколько секунд.");
    } else {
      error.value = r.detail ?? "Не удалось отправить.";
    }
  } catch (e) {
    error.value = formatError(e);
  } finally {
    testSending.value = false;
  }
}

// ─── Notification prefs ─────────────────────────────────────────────────

const savingPrefs = ref(false);
async function patchPref(field: keyof TelegramPref, value: unknown) {
  if (!prefs.value) return;
  savingPrefs.value = true;
  // optimistic
  (prefs.value as any)[field] = value;
  try {
    prefs.value = await mfaApi.updatePrefs({ [field]: value });
  } catch (e) {
    error.value = formatError(e);
    await refresh();
  } finally {
    savingPrefs.value = false;
  }
}

const linkUiState = computed(() => {
  if (!status.value) return "loading";
  if (linkDeepLink.value) return "linking";
  if (status.value.telegram_linked && status.value.enabled) return "linked-with-mfa";
  if (status.value.telegram_linked && !status.value.enabled) return "linked-no-mfa";
  return "not-linked";
});

const linkExpiresIn = computed(() => {
  if (!linkExpiresAt.value) return "";
  const ms = new Date(linkExpiresAt.value).getTime() - Date.now();
  if (ms <= 0) return "истёк";
  return `${Math.ceil(ms / 60000)} мин`;
});
</script>

<template>
  <div class="ss-page">
    <div class="ss-topbar">
      <div class="ss-eyebrow">UzAssets · настройки</div>
      <div class="ss-title">Безопасность</div>
      <div class="ss-sub">Двухфакторная аутентификация и уведомления через Telegram</div>
    </div>

    <div v-if="loading" class="ss-loading">Загрузка…</div>

    <transition name="uza-fade">
      <div v-if="notice" class="ss-notice">{{ notice }}</div>
    </transition>
    <transition name="uza-fade">
      <div v-if="error" class="ss-error">
        {{ error }}
        <button class="ss-error-close" @click="error = null">×</button>
      </div>
    </transition>

    <!-- ─── Section 1: Telegram link ─── -->
    <section v-if="status" class="ss-card">
      <div class="ss-card-head">
        <div class="ss-card-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M22 2 11 13"/><path d="m22 2-7 20-4-9-9-4 20-7Z"/>
          </svg>
        </div>
        <div class="ss-card-title">Telegram</div>
        <div class="ss-card-pill" :class="{
          'pill-green': linkUiState === 'linked-with-mfa' || linkUiState === 'linked-no-mfa',
          'pill-grey':  linkUiState === 'not-linked',
        }">
          {{ linkUiState === 'not-linked' ? 'не привязан' : 'привязан' }}
        </div>
      </div>

      <!-- Not linked -->
      <div v-if="linkUiState === 'not-linked'" class="ss-card-body">
        <p class="ss-desc">
          Привяжите Telegram, чтобы получать коды для 2FA и уведомления о задачах и дедлайнах.
        </p>
        <button class="ss-btn-primary" @click="startLink">Связать Telegram</button>
      </div>

      <!-- Linking in progress (deep link issued) -->
      <div v-else-if="linkUiState === 'linking'" class="ss-card-body">
        <p class="ss-desc">Откройте ссылку и нажмите Start в боте.</p>
        <a :href="linkDeepLink!" target="_blank" rel="noopener" class="ss-deep-link">
          {{ linkDeepLink }}
        </a>
        <div class="ss-link-meta">
          Срок действия: {{ linkExpiresIn }}.
          <span v-if="linkPolling">Ожидание подтверждения…</span>
        </div>
        <button class="ss-btn-ghost" @click="cancelLink">Отмена</button>
      </div>

      <!-- Linked -->
      <div v-else class="ss-card-body">
        <div class="ss-info-row">
          <span class="ss-label">Аккаунт:</span>
          <span class="ss-value">{{ status.telegram_username ? '@' + status.telegram_username : 'без username' }}</span>
        </div>
        <div class="ss-info-row" v-if="status.telegram_linked_at">
          <span class="ss-label">Привязан:</span>
          <span class="ss-value">{{ fmt.fmtDateTime(status.telegram_linked_at) }}</span>
        </div>
        <div class="ss-actions">
          <button class="ss-btn-ghost" :disabled="testSending" @click="sendTest">
            {{ testSending ? "Отправка…" : "Отправить тест" }}
          </button>
          <button class="ss-btn-danger" @click="unlinkModalOpen = true">Отвязать</button>
        </div>
      </div>
    </section>

    <!-- ─── Section 2: 2FA ─── -->
    <section v-if="status" class="ss-card">
      <div class="ss-card-head">
        <div class="ss-card-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="11" width="18" height="11" rx="2"/>
            <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
          </svg>
        </div>
        <div class="ss-card-title">Двухфакторная аутентификация</div>
        <div class="ss-card-pill" :class="{ 'pill-green': status.enabled, 'pill-grey': !status.enabled }">
          {{ status.enabled ? 'включена' : 'отключена' }}
        </div>
      </div>

      <div v-if="!status.enabled" class="ss-card-body">
        <p class="ss-desc">
          При входе на платформу мы будем отправлять одноразовый код в Telegram. Дополнительно
          вы получите 10 recovery-кодов на случай потери доступа к телефону.
        </p>
        <button
          class="ss-btn-primary"
          :disabled="!status.telegram_linked"
          @click="enable2fa"
        >
          Включить 2FA
        </button>
        <p v-if="!status.telegram_linked" class="ss-warn">
          Сначала привяжите Telegram.
        </p>
      </div>

      <div v-else class="ss-card-body">
        <div class="ss-info-row">
          <span class="ss-label">Метод:</span>
          <span class="ss-value">{{ status.method === 'telegram' ? 'Telegram' : status.method }}</span>
        </div>
        <div class="ss-info-row">
          <span class="ss-label">Recovery-коды:</span>
          <span class="ss-value">
            {{ status.recovery_codes_remaining }} из {{ status.recovery_codes_total }} осталось
          </span>
        </div>
        <div class="ss-actions">
          <button class="ss-btn-ghost" @click="regenModalOpen = true">
            Сгенерировать заново
          </button>
          <button class="ss-btn-danger" @click="disableModalOpen = true">
            Отключить 2FA
          </button>
        </div>
      </div>
    </section>

    <!-- ─── Section 3: Notification preferences ─── -->
    <section v-if="status?.telegram_linked && prefs" class="ss-card">
      <div class="ss-card-head">
        <div class="ss-card-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/>
            <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>
          </svg>
        </div>
        <div class="ss-card-title">Уведомления</div>
      </div>
      <div class="ss-card-body">
        <p class="ss-desc">
          Дублирование уведомлений из платформы в Telegram. Изменения сохраняются автоматически.
        </p>

        <div class="ss-toggle-row">
          <div>
            <div class="ss-toggle-name">Уведомления включены</div>
            <div class="ss-toggle-hint">Главный переключатель — отключает всё ниже</div>
          </div>
          <label class="ss-switch">
            <input
              type="checkbox"
              :checked="prefs.enabled"
              @change="patchPref('enabled', ($event.target as HTMLInputElement).checked)"
            />
            <span class="ss-switch-track"></span>
          </label>
        </div>

        <div class="ss-divider"></div>

        <div v-for="(label, field) in {
          type_assignments: 'Назначения задач',
          type_mentions:    'Упоминания (@me)',
          type_deadlines:   'Дедлайны и просрочки',
          type_moderation:  'Очередь модерации',
          type_broadcasts:  'Рассылки администратора',
          type_system:      'Системные уведомления',
        }" :key="field" class="ss-toggle-row ss-toggle-row-thin">
          <div class="ss-toggle-name">{{ label }}</div>
          <label class="ss-switch">
            <input
              type="checkbox"
              :checked="(prefs as any)[field]"
              :disabled="!prefs.enabled"
              @change="patchPref(field as keyof TelegramPref, ($event.target as HTMLInputElement).checked)"
            />
            <span class="ss-switch-track"></span>
          </label>
        </div>

        <div class="ss-divider"></div>

        <div class="ss-toggle-row">
          <div>
            <div class="ss-toggle-name">Тихие часы</div>
            <div class="ss-toggle-hint">Не беспокоить в указанный период (критичные обходят)</div>
          </div>
          <label class="ss-switch">
            <input
              type="checkbox"
              :checked="prefs.quiet_hours_enabled"
              :disabled="!prefs.enabled"
              @change="patchPref('quiet_hours_enabled', ($event.target as HTMLInputElement).checked)"
            />
            <span class="ss-switch-track"></span>
          </label>
        </div>
        <div v-if="prefs.quiet_hours_enabled" class="ss-quiet-times">
          <div>
            <label class="ss-label">Начало</label>
            <input
              type="time"
              :value="(prefs.quiet_hours_start || '22:00:00').slice(0, 5)"
              :disabled="!prefs.enabled"
              class="ss-input"
              @change="patchPref('quiet_hours_start', ($event.target as HTMLInputElement).value + ':00')"
            />
          </div>
          <div>
            <label class="ss-label">Конец</label>
            <input
              type="time"
              :value="(prefs.quiet_hours_end || '07:00:00').slice(0, 5)"
              :disabled="!prefs.enabled"
              class="ss-input"
              @change="patchPref('quiet_hours_end', ($event.target as HTMLInputElement).value + ':00')"
            />
          </div>
        </div>
      </div>
    </section>

    <!-- ─── Recovery codes modal ─── -->
    <div v-if="showRecoveryCodes" class="ss-modal-backdrop" @click.self="dismissRecoveryCodes">
      <div class="ss-modal">
        <div class="ss-modal-head">
          <h3>Recovery-коды</h3>
          <button class="ss-modal-x" @click="dismissRecoveryCodes">×</button>
        </div>
        <div class="ss-modal-body">
          <p class="ss-warn-strong">
            Сохраните эти коды в надёжном месте. Это единственный раз, когда они отображаются.
            Каждый код можно использовать один раз для входа при потере доступа к Telegram.
          </p>
          <div class="ss-codes-grid">
            <div v-for="code in recoveryCodes" :key="code" class="ss-code">{{ code }}</div>
          </div>
          <div class="ss-modal-actions">
            <button class="ss-btn-ghost" @click="copyRecoveryCodes">Скопировать все</button>
            <button class="ss-btn-primary" @click="dismissRecoveryCodes">Я сохранил, закрыть</button>
          </div>
        </div>
      </div>
    </div>

    <!-- ─── Disable 2FA modal ─── -->
    <div v-if="disableModalOpen" class="ss-modal-backdrop" @click.self="disableModalOpen = false">
      <div class="ss-modal ss-modal-narrow">
        <div class="ss-modal-head">
          <h3>Отключить 2FA</h3>
          <button class="ss-modal-x" @click="disableModalOpen = false">×</button>
        </div>
        <div class="ss-modal-body">
          <p>Для отключения введите один из ваших recovery-кодов:</p>
          <input
            v-model="disableCode"
            type="text"
            placeholder="XXXX-XXXX"
            class="ss-input ss-input-mono"
          />
          <div class="ss-modal-actions">
            <button class="ss-btn-ghost" @click="disableModalOpen = false">Отмена</button>
            <button
              class="ss-btn-danger"
              :disabled="disableCode.trim().length < 8"
              @click="confirmDisable"
            >
              Отключить
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- ─── Unlink Telegram modal ─── -->
    <div v-if="unlinkModalOpen" class="ss-modal-backdrop" @click.self="unlinkModalOpen = false">
      <div class="ss-modal ss-modal-narrow">
        <div class="ss-modal-head">
          <h3>Отвязать Telegram</h3>
          <button class="ss-modal-x" @click="unlinkModalOpen = false">×</button>
        </div>
        <div class="ss-modal-body">
          <p>Уведомления и коды 2FA больше не будут приходить в Telegram.</p>
          <p v-if="status?.enabled && status?.method === 'telegram'" class="ss-warn-strong">
            При отвязке 2FA будет автоматически отключена.
          </p>
          <div class="ss-modal-actions">
            <button class="ss-btn-ghost" @click="unlinkModalOpen = false">Отмена</button>
            <button class="ss-btn-danger" @click="confirmUnlink">Отвязать</button>
          </div>
        </div>
      </div>
    </div>

    <!-- ─── Regenerate recovery codes modal ─── -->
    <div v-if="regenModalOpen" class="ss-modal-backdrop" @click.self="regenModalOpen = false">
      <div class="ss-modal ss-modal-narrow">
        <div class="ss-modal-head">
          <h3>Сгенерировать новые recovery-коды</h3>
          <button class="ss-modal-x" @click="regenModalOpen = false">×</button>
        </div>
        <div class="ss-modal-body">
          <p>
            Текущие 10 кодов будут <strong>немедленно</strong> заменены новыми.
            После закрытия экрана с новыми кодами они больше не отобразятся.
          </p>
          <div class="ss-modal-actions">
            <button class="ss-btn-ghost" @click="regenModalOpen = false">Отмена</button>
            <button class="ss-btn-primary" @click="confirmRegenerate">Сгенерировать</button>
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
</style>
