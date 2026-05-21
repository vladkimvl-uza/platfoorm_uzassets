<script setup lang="ts">
/**
 * Module page — lists all endpoints in a module (e.g. /api-docs/endpoints/financials).
 */
import { computed, onMounted } from "vue";
import { useRoute } from "vue-router";
import { useApiCatalogStore } from "@/stores/apiCatalog";
import EndpointCard from "@/components/library/EndpointCard.vue";

const route = useRoute();
const catalog = useApiCatalogStore();

const moduleCode = computed(() => String(route.params.module || ""));

onMounted(() => catalog.loadSummary());

const moduleMeta = computed(() => {
  if (!catalog.summary) return null;
  return catalog.summary.modules.find(m => m.name === moduleCode.value) || null;
});

const endpoints = computed(() => {
  if (!catalog.summary) return [];
  return catalog.summary.endpoints
    .filter(e => (e.module || "") === moduleCode.value)
    .sort((a, b) => {
      const ord = ["GET", "POST", "PATCH", "PUT", "DELETE", "WEBSOCKET"];
      return ord.indexOf(a.method) - ord.indexOf(b.method) || a.path.localeCompare(b.path);
    });
});
</script>

<template>
  <article class="mp">
    <header class="mp-head">
      <div class="mp-eyebrow">Модуль</div>
      <h1 class="mp-h1">{{ moduleCode }}</h1>
      <p v-if="moduleMeta" class="mp-sub">
        Группа: <b>{{ moduleMeta.group || "Прочее" }}</b>
        · {{ moduleMeta.endpoints_count }} endpoints
      </p>
    </header>

    <div v-if="!catalog.summary" class="mp-loading">Загружаю каталог…</div>
    <div v-else-if="endpoints.length === 0" class="mp-empty">В этом модуле endpoints не найдены.</div>

    <div v-else class="mp-list">
      <EndpointCard
        v-for="e in endpoints"
        :key="e.method + ':' + e.path"
        :endpoint="(e as any)"
      />
    </div>
  </article>
</template>

<style scoped>
.mp { max-width: 760px; }
.mp-head { margin-bottom: 22px; }
.mp-eyebrow { font-size: 10.5px; letter-spacing: 0.08em; text-transform: uppercase; color: #888780; font-weight: 500; }
.mp-h1 { font-size: 24px; font-weight: 500; color: #1E2A4A; letter-spacing: -0.01em; margin: 4px 0 0 0; font-family: ui-monospace, "SF Mono", Menlo, monospace; }
.mp-sub { font-size: 12.5px; color: #888780; margin-top: 4px; }

.mp-list { display: flex; flex-direction: column; gap: 8px; }
.mp-loading, .mp-empty { padding: 32px; text-align: center; color: #888780; font-size: 13px; }
</style>
