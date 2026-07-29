<template>
  <article class="dp">
    <h1 class="dp-h1">Rate limits</h1>
    <p class="dp-lead">{{ t('Защита от credential-stuffing и API-abuse. При превышении — статус') }} <code>429 Too Many Requests</code>.</p>

    <table class="dp-table">
      <thead>
        <tr><th>Zone</th><th>{{ t('Лимит') }}</th><th>Burst</th><th>{{ t('Применяется к') }}</th></tr>
      </thead>
      <tbody>
        <tr><td><b>auth_zone</b></td><td>{{ t('10 / мин') }}</td><td>5</td><td><code>/auth/login</code>, <code>/auth/refresh</code>, <code>/auth/login-mfa</code></td></tr>
        <tr><td><b>api_zone</b></td><td>{{ t('1200 / мин') }}</td><td>200</td><td>{{ t('Все остальные') }} <code>/api/*</code></td></tr>
        <tr><td><b>heavy_zone</b></td><td>{{ t('60 / мин') }}</td><td>10</td><td>Reports, exports — <code>/api/reports/*</code>, <code>/api/export/*</code></td></tr>
      </tbody>
    </table>

    <h2 class="dp-h2">{{ t('Обработка 429') }}</h2>
    <p>{{ t('Клиент должен делать exponential back-off: 1s → 2s → 4s → 8s, с max 30s. Header') }} <code>Retry-After</code> {{ t('(если присутствует) — рекомендованная пауза.') }}</p>

    <pre class="dp-code">{{ t('// JS пример с back-off async function fetchWithRetry(url, init, maxRetries = 5) { for (let i = 0; i &lt; maxRetries; i++) { const r = await fetch(url, init); if (r.status !== 429) return r; const wait = Math.min(30000, 1000 * Math.pow(2, i)); await new Promise(res => setTimeout(res, wait)); } throw new Error("Rate limited too many times"); }') }}</pre>
  </article>
</template>

<script setup lang="ts">
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();
</script>

<style scoped>
.dp { max-width: 720px; }
.dp-h1 { font-size: 24px; font-weight: 500; color: var(--t1, #1E2A4A); letter-spacing: -0.01em; margin: 0 0 12px 0; }
.dp-h2 { font-size: 15px; font-weight: 500; color: var(--t1, #1E2A4A); margin: 24px 0 8px 0; }
.dp-lead { font-size: 14px; color: #444; line-height: 1.55; margin-bottom: 18px; }
.dp-table { width: 100%; border-collapse: separate; border-spacing: 0; background: white; border: 0.5px solid #F1EFE8; border-radius: 10px; overflow: hidden; font-size: 12.5px; }
.dp-table th { background: var(--bg2, #FAFAFC); text-align: left; padding: 9px 12px; font-size: 10.5px; font-weight: 500; letter-spacing: 0.04em; text-transform: uppercase; color: var(--t3, var(--t-muted)); border-bottom: 0.5px solid #F1EFE8; }
.dp-table td { padding: 9px 12px; border-bottom: 0.5px solid #F4F4F2; color: var(--t1, #1E2A4A); vertical-align: top; }
.dp-table tr:last-child td { border-bottom: none; }
.dp-table code { font-family: ui-monospace, Menlo, monospace; font-size: 11px; color: var(--p-deep); background: rgba(127,119,221,.06); padding: 1px 4px; border-radius: 3px; }
.dp-code { background: #1E2A4A; color: var(--border-input); padding: 14px 16px; border-radius: 10px; font-family: ui-monospace, Menlo, monospace; font-size: 11.5px; line-height: 1.5; overflow-x: auto; margin: 10px 0; }
</style>
