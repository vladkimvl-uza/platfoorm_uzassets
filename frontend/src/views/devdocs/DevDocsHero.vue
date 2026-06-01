<script setup lang="ts">
import { onMounted, ref } from "vue";
import { apiCatalog, type CatalogStatus } from "@/api/apiCatalog";

const status = ref<CatalogStatus | null>(null);

onMounted(async () => {
  try { status.value = await apiCatalog.status(); } catch { /* ignore */ }
});
</script>

<template>
  <section class="dh-hero">
    <div class="dh-inner">
      <div class="dh-text">
        <div class="dh-eyebrow">UzAssets Platform · API</div>
        <h1 class="dh-title">API для интеграции с платформой</h1>
        <p class="dh-desc">
          Дёргайте финансовые показатели, KPI, рейтинги, кредитный портфель и закупки
          напрямую из своих систем. REST · WebSocket · webhooks.
        </p>
        <div class="dh-cta">
          <RouterLink to="/api-docs/authentication" class="dh-btn dh-btn-primary">
            Получить токен →
          </RouterLink>
          <RouterLink to="/api-docs/endpoints/companies" class="dh-btn dh-btn-secondary">
            Каталог endpoints
          </RouterLink>
        </div>
      </div>

      <div v-if="status" class="dh-status">
        <div class="dh-status-row">
          <span class="dh-stat-dot" :class="{ 'dh-stat-on': status.operational }"></span>
          <span class="dh-stat-label">
            {{ status.operational ? "Operational" : "Degraded" }}
          </span>
        </div>
        <div class="dh-status-meta">
          <span>{{ status.title }}</span>
          <span class="dh-status-sep">·</span>
          <span>v{{ status.version }}</span>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.dh-hero {
  background: linear-gradient(135deg, #1E2A4A 0%, var(--p-deep) 100%);
  color: white;
  padding: 48px 36px;
}
.dh-inner { display: flex; justify-content: space-between; align-items: flex-start; gap: 24px; max-width: 1200px; margin: 0 auto; }

.dh-text { flex: 1; max-width: 640px; }
.dh-eyebrow { font-size: 10.5px; letter-spacing: 0.08em; text-transform: uppercase; color: rgba(255,255,255,.7); font-weight: 500; }
.dh-title { font-size: 32px; font-weight: 500; letter-spacing: -0.015em; margin: 8px 0 14px 0; line-height: 1.15; }
.dh-desc { font-size: 14px; color: rgba(255,255,255,.85); line-height: 1.6; max-width: 540px; margin: 0; }

.dh-cta { display: flex; gap: 10px; margin-top: 22px; flex-wrap: wrap; }
.dh-btn {
  padding: 9px 18px;
  border-radius: 9px;
  font-size: 13px; font-weight: 500;
  text-decoration: none;
  transition: all 150ms;
}
.dh-btn-primary { background: white; color: var(--t1, #1E2A4A); }
.dh-btn-primary:hover { background: rgba(255,255,255,.92); transform: translateY(-1px); }
.dh-btn-secondary { background: transparent; color: white; border: 1px solid rgba(255,255,255,.3); }
.dh-btn-secondary:hover { background: rgba(255,255,255,.10); }

.dh-status {
  background: rgba(255,255,255,.08);
  border: 1px solid rgba(255,255,255,.16);
  border-radius: 10px;
  padding: 12px 16px;
  display: flex; flex-direction: column; gap: 6px;
  min-width: 200px;
  flex-shrink: 0;
}
.dh-status-row { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 500; }
.dh-stat-dot { width: 8px; height: 8px; border-radius: 50%; background: #C8C7C0; }
.dh-stat-on  { background: #34D399; box-shadow: 0 0 0 0 rgba(52, 211, 153, 0.6); animation: dhStatusPulse 2s ease-out infinite; }
@keyframes dhStatusPulse { 0%, 100% { box-shadow: 0 0 0 0 rgba(52, 211, 153, 0.6); } 50% { box-shadow: 0 0 0 5px rgba(52, 211, 153, 0); } }
.dh-status-meta { font-size: 11.5px; color: rgba(255,255,255,.7); display: flex; gap: 5px; }
.dh-status-sep  { opacity: 0.5; }

@media (max-width: 900px) {
  .dh-inner { flex-direction: column; }
  .dh-title { font-size: 26px; }
}
</style>
