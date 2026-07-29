<template>
  <article class="dp">
    <h1 class="dp-h1">{{ t('Аутентификация') }}</h1>
    <p class="dp-lead">{{ t('Платформа использует JWT (HS256/RS256). Все запросы кроме') }} <code>/auth/*</code> {{ t('требуют header') }} <code>Authorization: Bearer &lt;token&gt;</code>.</p>

    <section class="dp-section">
      <h2 class="dp-h2">{{ t('1. Получение токена') }}</h2>
      <pre class="dp-code">POST /api/auth/login
Content-Type: application/json

&#123;
  "login":    "v.kim@uz-assets.uz",
  "password": "&lt;your_password&gt;"
&#125;</pre>
      <p>{{ t('Ответ:') }}</p>
      <pre class="dp-code">{
  "access_token":  "eyJhbGc...",
  "refresh_token": "eyJhbGc...",
  "token_type":    "Bearer",
  "expires_in":    1800
}</pre>
    </section>

    <section class="dp-section">
      <h2 class="dp-h2">{{ t('2. Использование токена') }}</h2>
      <pre class="dp-code">curl -X GET 'https://platform.uz-assets.uz/api/companies' \
  -H 'Authorization: Bearer eyJhbGc...'</pre>
    </section>

    <section class="dp-section">
      <h2 class="dp-h2">{{ t('3. Обновление токена') }}</h2>
      <p><b>access_token</b> {{ t('живёт 30 мин. Используйте') }} <code>/auth/refresh</code> {{ t('с refresh-токеном для получения нового. Refresh ротируется — старый аннулируется.') }}</p>
      <pre class="dp-code">POST /api/auth/refresh
{ "refresh_token": "eyJhbGc..." }</pre>
    </section>

    <section class="dp-section">
      <h2 class="dp-h2">4. MFA (2FA)</h2>
      <p>{{ t('Если у пользователя включена 2FA,') }} <code>/auth/login</code> {{ t('вернёт 200 с') }} <code>{"need_mfa": true, "mfa_token": "..."}</code>{{ t('. Вторым шагом —') }} <code>POST /auth/login-mfa</code> {{ t('с кодом из Telegram или TOTP.') }}</p>
    </section>

    <section class="dp-section">
      <h2 class="dp-h2">5. Permissions (scopes)</h2>
      <p>{{ t('Каждый endpoint защищён правом из RBAC v3 (например') }} <code>kpi.edit</code>, <code>moderation.review</code>{{ t('). На странице каждого endpoint\'а — required permission. Если у пользователя нет права — backend возвращает 403.') }}</p>
    </section>
  </article>
</template>

<script setup lang="ts">
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();
</script>

<style scoped>
.dp { max-width: 720px; }
.dp-h1 { font-size: 24px; font-weight: 500; color: var(--t1, #1E2A4A); letter-spacing: -0.01em; margin: 0 0 12px 0; }
.dp-h2 { font-size: 15px; font-weight: 500; color: var(--t1, #1E2A4A); margin: 0 0 8px 0; }
.dp-lead { font-size: 14px; color: #444; line-height: 1.6; margin-bottom: 24px; }
.dp-section { margin-bottom: 28px; }
.dp-section p { font-size: 13px; color: #444; line-height: 1.55; margin: 6px 0; }
.dp-section code { font-family: ui-monospace, Menlo, monospace; background: rgba(127,119,221,.08); color: var(--p-deep); padding: 1px 5px; border-radius: 4px; font-size: 11.5px; }
.dp-code {
  background: #1E2A4A; color: var(--border-input);
  padding: 14px 16px; border-radius: 10px;
  font-family: ui-monospace, Menlo, monospace;
  font-size: 12px; line-height: 1.5;
  overflow-x: auto;
  margin: 8px 0;
  white-space: pre-wrap; word-wrap: break-word;
}
</style>
