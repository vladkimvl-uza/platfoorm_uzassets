<template>
  <footer class="df-foot">
    <div class="df-row">
      <span class="df-brand">{{ t('UzAssets · Платформа управления портфелем') }}</span>
      <div class="df-links">
        <a href="/api/api-catalog/openapi.json" target="_blank">OpenAPI JSON</a>
        <a href="/api/api-catalog/postman.json" target="_blank">Postman collection</a>
        <RouterLink to="/api-docs">Quickstart</RouterLink>
        <a href="mailto:v.kim@uz-assets.uz">{{ t('Поддержка') }}</a>
      </div>
    </div>
  </footer>
</template>

<script setup lang="ts">
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();
</script>

<style scoped>
.df-foot {
  border-top: 0.5px solid #F1EFE8;
  padding: 14px 28px;
  background: white;
}
.df-row {
  display: flex; justify-content: space-between; align-items: center;
  max-width: 1200px; margin: 0 auto;
  flex-wrap: wrap; gap: 12px;
}
.df-brand { font-size: 11px; color: var(--t3, var(--t-muted)); }
.df-links { display: flex; gap: 18px; font-size: 11.5px; }
.df-links a { color: var(--p-deep); text-decoration: none; }
.df-links a:hover { text-decoration: underline; }
</style>
