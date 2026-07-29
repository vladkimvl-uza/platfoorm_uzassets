<script setup lang="ts">
/**
 * EmailSettings — админ-настройка SMTP / email-уведомлений.
 *
 * Параметры хранятся в БД (system_config) и применяются без передеплоя.
 * Доступ: OWNER или admin.users. Пароль не отображается (только флаг
 * наличия) — оставьте поле пустым, чтобы не менять.
 */
import { ref, reactive, computed, onMounted } from "vue";
import { emailSettingsApi, type EmailSettings } from "@/api/emailSettings";
import { useAuthStore } from "@/stores/auth";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();


const auth = useAuthStore();
const canManage = computed(() => !!auth.user?.is_owner || auth.hasPermission?.("admin.users"));

const loading = ref(true);
const saving = ref(false);
const testing = ref(false);
const error = ref<string | null>(null);
const ok = ref<string | null>(null);
const passwordSet = ref(false);

const form = reactive({
  SMTP_ENABLED: false,
  SMTP_HOST: "",
  SMTP_PORT: 587,
  SMTP_USER: "",
  SMTP_PASSWORD: "",          // пустое = не менять
  SMTP_FROM: "UzAssets <no-reply@uz-assets.uz>",
  SMTP_USE_TLS: true,
  SMTP_USE_SSL: false,
  SMTP_VERIFY_CERT: true,
  PUBLIC_URL: "https://platform.uz-assets.uz",
});

function fill(s: EmailSettings) {
  form.SMTP_ENABLED = s.SMTP_ENABLED;
  form.SMTP_HOST = s.SMTP_HOST || "";
  form.SMTP_PORT = s.SMTP_PORT || 587;
  form.SMTP_USER = s.SMTP_USER || "";
  form.SMTP_FROM = s.SMTP_FROM || form.SMTP_FROM;
  form.SMTP_USE_TLS = s.SMTP_USE_TLS;
  form.SMTP_USE_SSL = s.SMTP_USE_SSL;
  form.SMTP_VERIFY_CERT = s.SMTP_VERIFY_CERT;
  form.PUBLIC_URL = s.PUBLIC_URL || form.PUBLIC_URL;
  passwordSet.value = s.SMTP_PASSWORD_SET;
  form.SMTP_PASSWORD = "";
}

onMounted(async () => {
  try { fill(await emailSettingsApi.get()); }
  catch (e: any) { error.value = e?.response?.data?.detail || t('Не удалось загрузить настройки'); }
  finally { loading.value = false; }
});

// SSL (465) и STARTTLS (587) взаимоисключающие
function onSslToggle() { if (form.SMTP_USE_SSL) { form.SMTP_USE_TLS = false; if (form.SMTP_PORT === 587) form.SMTP_PORT = 465; } }
function onTlsToggle() { if (form.SMTP_USE_TLS) { form.SMTP_USE_SSL = false; if (form.SMTP_PORT === 465) form.SMTP_PORT = 587; } }

async function save() {
  saving.value = true; error.value = null; ok.value = null;
  try {
    const payload: any = { ...form };
    if (!payload.SMTP_PASSWORD) delete payload.SMTP_PASSWORD;  // пустое = не менять
    fill(await emailSettingsApi.update(payload));
    ok.value = t("Настройки сохранены");
    setTimeout(() => { ok.value = null; }, 2500);
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('Не удалось сохранить');
  } finally { saving.value = false; }
}

async function sendTest() {
  testing.value = true; error.value = null; ok.value = null;
  try {
    const r = await emailSettingsApi.sendTest();
    ok.value = t("Тестовое письмо отправлено на {email}", { email: r.to });
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('Не удалось отправить тестовое письмо');
  } finally { testing.value = false; }
}
</script>

<template>
  <div class="es-wrap">
    <header class="es-hdr">
      <div class="es-eyebrow">{{ t('Уведомления · канал e-mail') }}</div>
      <h1 class="es-title">{{ t('Настройка SMTP') }}</h1>
      <p class="es-sub">{{ t('Параметры применяются сразу, без передеплоя. Пароль не отображается — оставьте пустым, чтобы не менять.') }}</p>
    </header>

    <div v-if="!canManage" class="es-card es-deny">{{ t('Недостаточно прав. Требуется OWNER или admin.users.') }}</div>
    <div v-else-if="loading" class="es-card">{{ t('Загрузка…') }}</div>

    <div v-else class="es-card">
      <!-- Главный тумблер -->
      <label class="es-switch-row">
        <span>
          <span class="es-switch-title">{{ t('Отправка писем включена') }}</span>
          <span class="es-switch-sub">{{ t('Когда выключено — письма не отправляются (логируются).') }}</span>
        </span>
        <input type="checkbox" v-model="form.SMTP_ENABLED" class="es-switch" />
      </label>

      <div class="es-grid">
        <label class="es-field">
          <span class="es-lbl">{{ t('SMTP-сервер (host)') }}</span>
          <input v-model="form.SMTP_HOST" class="es-in" placeholder="smtp.yandex.ru" />
        </label>
        <label class="es-field es-field-sm">
          <span class="es-lbl">{{ t('Порт') }}</span>
          <input v-model.number="form.SMTP_PORT" type="number" class="es-in" placeholder="587" />
        </label>
        <label class="es-field">
          <span class="es-lbl">{{ t('Логин (SMTP user)') }}</span>
          <input v-model="form.SMTP_USER" class="es-in" placeholder="no-reply@uz-assets.uz" />
        </label>
        <label class="es-field">
          <span class="es-lbl">{{ t('Пароль') }} <span v-if="passwordSet" class="es-pwd-set">{{ t('(задан — оставьте пустым, чтобы не менять)') }}</span></span>
          <input v-model="form.SMTP_PASSWORD" type="password" class="es-in" :placeholder="passwordSet ? '••••••••' : t('пароль приложения')" autocomplete="new-password" />
        </label>
        <label class="es-field es-field-wide">
          <span class="es-lbl">{{ t('Отправитель (From)') }}</span>
          <input v-model="form.SMTP_FROM" class="es-in" placeholder="UzAssets &lt;no-reply@uz-assets.uz&gt;" />
        </label>
      </div>

      <div class="es-tls">
        <label class="es-check"><input type="checkbox" v-model="form.SMTP_USE_TLS" @change="onTlsToggle" /><span>{{ t('STARTTLS (порт 587)') }}</span></label>
        <label class="es-check"><input type="checkbox" v-model="form.SMTP_USE_SSL" @change="onSslToggle" /><span>{{ t('SSL/TLS (порт 465)') }}</span></label>
        <label class="es-check"><input type="checkbox" v-model="form.SMTP_VERIFY_CERT" /><span>{{ t('Проверять сертификат') }}</span></label>
      </div>
      <p class="es-tls-note">{{ t('Корпоративный Exchange: порт') }} <b>25</b>{{ t(', STARTTLS и SSL') }} <b>{{ t('выключены') }}</b>{{ t(', логин/пароль') }} <b>{{ t('пустые') }}</b> {{ t('(анонимный релей с доверенного IP). Если включаете STARTTLS с самоподписанным сертификатом — снимите «Проверять сертификат».') }}</p>

      <label class="es-field es-field-wide" style="margin-top:14px">
        <span class="es-lbl">{{ t('Публичный URL платформы (для ссылок в письмах)') }}</span>
        <input v-model="form.PUBLIC_URL" class="es-in" placeholder="https://platform.uz-assets.uz" />
      </label>

      <p v-if="error" class="es-msg es-err">{{ error }}</p>
      <Transition name="fade">
        <p v-if="ok" class="es-msg es-ok">{{ ok }}</p>
      </Transition>

      <div class="es-actions">
        <button class="es-btn es-ghost" :disabled="testing || !form.SMTP_ENABLED" @click="sendTest">
          {{ testing ? t('Отправка…') : t('✉ Отправить тестовое письмо себе') }}
        </button>
        <button class="es-btn es-primary" :disabled="saving" @click="save">
          {{ saving ? t('Сохранение…') : t('Сохранить') }}
        </button>
      </div>
    </div>

    <div v-if="canManage && !loading" class="es-hint">
      <b>{{ t('Подсказки по провайдерам:') }}</b> Yandex — host <code>smtp.yandex.ru</code>{{ t(', порт') }} <code>465</code>, SSL;
      Gmail — <code>smtp.gmail.com</code>:<code>587</code>{{ t(', STARTTLS (нужен «пароль приложения»); корпоративный — уточните у администратора почты. Шаблоны писем — фирменные (см. превью в docs/).') }}
    </div>
  </div>
</template>

<style scoped>
.es-wrap { max-width: 720px; margin: 0 auto; padding: 24px 20px; }
.es-hdr { margin-bottom: 18px; }
.es-eyebrow { font-size: 10px; font-weight: 500; text-transform: uppercase; letter-spacing: .07em; color: var(--t3, #64748B); }
.es-title { font-size: 22px; font-weight: 600; letter-spacing: -.02em; color: var(--navy-heading, #1E2A4A); margin: 4px 0 6px; }
.es-sub { font-size: 13px; color: var(--t3, #64748B); margin: 0; }
.es-card { background: var(--card-bg, #fff); border: 1px solid var(--card-border, #E5E7EB); border-radius: 14px; padding: 20px 22px; }
.es-deny { color: var(--sev-high, #E24B4A); font-size: 13px; }
.es-switch-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding-bottom: 16px; margin-bottom: 16px; border-bottom: 1px solid var(--border-hard, #E5E7EB); cursor: pointer; }
.es-switch-title { display: block; font-size: 14px; font-weight: 600; color: var(--t1, #1E2A4A); }
.es-switch-sub { display: block; font-size: 11.5px; color: var(--t3, #94A3B8); margin-top: 2px; }
.es-switch { width: 18px; height: 18px; accent-color: var(--green, #1D9E75); flex-shrink: 0; }
.es-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.es-field { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.es-field-wide { grid-column: 1 / -1; }
.es-field-sm { max-width: 140px; }
.es-lbl { font-size: 11px; font-weight: 500; color: var(--t3, #64748B); }
.es-pwd-set { color: var(--green, #1D9E75); font-weight: 400; text-transform: none; letter-spacing: 0; }
.es-in { width: 100%; box-sizing: border-box; padding: 9px 12px; border: 1.5px solid var(--border-input, #E2E8F0); border-radius: 9px; font-size: 13px; color: var(--t1, #1E2A4A); outline: none; font-family: inherit; background: var(--bg2, #F8FAFC); transition: border-color .14s, box-shadow .14s; }
.es-in:focus { border-color: var(--p, #7C6FF7); box-shadow: 0 0 0 3px rgba(124,111,247,.14); }
.es-tls { display: flex; flex-wrap: wrap; gap: 22px; margin-top: 14px; }
.es-tls-note { font-size: 11.5px; line-height: 1.5; color: var(--t3, #64748B); margin: 8px 0 0; padding: 9px 12px; background: var(--bg2, #F1F5F9); border-radius: 8px; }
.es-check { display: inline-flex; align-items: center; gap: 7px; font-size: 13px; color: var(--t2, #334155); cursor: pointer; }
.es-check input { width: 15px; height: 15px; accent-color: var(--p, #7C6FF7); }
.es-msg { font-size: 12.5px; margin: 14px 0 0; padding: 9px 12px; border-radius: 8px; }
.es-err { background: rgba(226,75,74,.08); border: 1px solid rgba(226,75,74,.3); color: #A82C2B; }
.es-ok { background: rgba(29,158,117,.10); border: 1px solid rgba(29,158,117,.3); color: #0F6E56; }
.fade-enter-active, .fade-leave-active { transition: opacity .22s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
.es-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 20px; }
.es-btn { padding: 10px 20px; border-radius: 9px; font-size: 13px; font-weight: 600; cursor: pointer; font-family: inherit; border: none; transition: all .14s; }
.es-btn:disabled { opacity: .55; cursor: not-allowed; }
.es-ghost { background: transparent; border: 1px solid var(--border-input, #E2E8F0); color: var(--t2, #334155); }
.es-ghost:hover:not(:disabled) { background: var(--bg3, #F1F5F9); }
.es-primary { background: linear-gradient(135deg, #8B7FFF 0%, #6C5CE7 100%); color: #fff; box-shadow: 0 2px 10px rgba(108,92,231,.32); }
.es-primary:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 4px 16px rgba(108,92,231,.45); }
.es-hint { margin-top: 16px; font-size: 12px; line-height: 1.6; color: var(--t3, #64748B); }
.es-hint code { font-family: ui-monospace, monospace; background: var(--bg2, #F1F5F9); padding: 1px 5px; border-radius: 4px; font-size: 11.5px; }
@media (max-width: 560px) { .es-grid { grid-template-columns: 1fr; } }
</style>
