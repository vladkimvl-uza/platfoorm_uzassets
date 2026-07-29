<template>
  <article class="dp">
    <h1 class="dp-h1">Webhooks</h1>
    <p class="dp-lead">{{ t('Платформа умеет push\'ить события на ваш HTTP endpoint в момент изменения данных. Подходит для синхронизации с CRM, ERP, BI.') }}</p>

    <section class="dp-section">
      <h2 class="dp-h2">Event types</h2>
      <ul class="dp-list">
        <li><code>company.field_updated</code> {{ t('— поле в библиотеке поменялось (любой модуль)') }}</li>
        <li><code>moderation.submitted</code> {{ t('— новая заявка на модерацию') }}</li>
        <li><code>moderation.resolved</code> {{ t('— заявка утверждена/отклонена') }}</li>
        <li><code>kpi.target_missed</code> {{ t('— KPI ниже целевого &lt;70%') }}</li>
        <li><code>credit.overdue</code> {{ t('— кредит вышел в просрочку') }}</li>
        <li><code>esg.issue_critical</code> {{ t('— критический ESG-инцидент') }}</li>
      </ul>
    </section>

    <section class="dp-section">
      <h2 class="dp-h2">Delivery</h2>
      <p>{{ t('POST с JSON-телом, header') }} <code>X-UzAssets-Signature: sha256=...</code> {{ t('(HMAC от secret, выданного при создании subscription). Ретраи: 5 попыток с back-off 1m → 5m → 15m → 1h → 6h.') }}</p>
    </section>

    <section class="dp-section">
      <h2 class="dp-h2">{{ t('Real-time WebSocket (альтернатива)') }}</h2>
      <p>{{ t('Если webhook overkill — есть live WS-канал') }} <code>/api/ws/companies</code> {{ t('и') }} <code>/api/ws/companies/&#123;id&#125;</code> {{ t('с тем же набором событий') }} <code>field_update</code>{{ t('. Подключение JWT-auth, экспоненциальный re-connect.') }}</p>
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
.dp-h2 { font-size: 15px; font-weight: 500; color: var(--t1, #1E2A4A); margin: 24px 0 8px 0; }
.dp-lead { font-size: 14px; color: #444; line-height: 1.55; }
.dp-section { margin: 18px 0; }
.dp-section code { font-family: ui-monospace, Menlo, monospace; background: rgba(127,119,221,.08); color: var(--p-deep); padding: 1px 5px; border-radius: 4px; font-size: 11.5px; }
.dp-list { padding-left: 20px; font-size: 13px; color: #444; line-height: 1.7; }
</style>
