<script setup lang="ts">
/**
 * DevDocs Sidebar — sections + module list from catalog summary.
 * Internal (authed-only) modules show as locked when not logged in.
 */
import { computed } from "vue";
import { useApiCatalogStore } from "@/stores/apiCatalog";
import { useAuthStore } from "@/stores/auth";

const catalog = useApiCatalogStore();
const auth    = useAuthStore();
const user    = computed(() => auth.user);

interface ModuleEntry { code: string; name: string; count: number; group: string }

const modulesAll = computed<ModuleEntry[]>(() => {
  if (!catalog.summary) return [];
  return catalog.summary.modules.map(m => ({
    code:  m.name,
    name:  m.name,
    count: m.endpoints_count,
    group: m.group || "Прочее",
  }));
});

const publicModules = computed(() =>
  modulesAll.value.filter(m => ["auth", "health", "api_catalog"].includes(m.code))
);
const internalModules = computed(() =>
  modulesAll.value.filter(m => !["auth", "health", "api_catalog"].includes(m.code))
);
</script>

<template>
  <aside class="ds-side">
    <section class="ds-section">
      <div class="ds-section-title">Getting started</div>
      <RouterLink to="/api-docs" class="ds-link" exact-active-class="active">Quickstart</RouterLink>
      <RouterLink to="/api-docs/authentication" class="ds-link" active-class="active">Аутентификация</RouterLink>
      <RouterLink to="/api-docs/rate-limits" class="ds-link" active-class="active">Rate limits</RouterLink>
      <RouterLink to="/api-docs/webhooks" class="ds-link" active-class="active">Webhooks</RouterLink>
      <RouterLink to="/api-docs/sdk" class="ds-link" active-class="active">SDK · TS + Python</RouterLink>
    </section>

    <section v-if="publicModules.length" class="ds-section">
      <div class="ds-section-title">Public endpoints</div>
      <RouterLink
        v-for="m in publicModules"
        :key="m.code"
        :to="`/api-docs/endpoints/${m.code}`"
        class="ds-link"
        active-class="active"
      >
        <span>{{ m.name }}</span>
        <span class="ds-count">{{ m.count }}</span>
      </RouterLink>
    </section>

    <section v-if="internalModules.length" class="ds-section">
      <div class="ds-section-title">
        Internal API
        <span v-if="!user" class="ds-lock" title="Требуется вход"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;margin-right:3px"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>authed</span>
      </div>
      <RouterLink
        v-for="m in internalModules"
        :key="m.code"
        :to="`/api-docs/endpoints/${m.code}`"
        class="ds-link"
        active-class="active"
        :class="{ 'ds-link-muted': !user }"
      >
        <span>{{ m.name }}</span>
        <span class="ds-count">{{ m.count }}</span>
      </RouterLink>
      <div v-if="!user" class="ds-login-hint">
        Для try-it-out на этих endpoints —
        <RouterLink to="/login?redirect=/api-docs">войдите</RouterLink>
      </div>
    </section>
  </aside>
</template>

<style scoped>
.ds-side {
  width: 240px;
  flex-shrink: 0;
  background: white;
  border-right: 0.5px solid #F1EFE8;
  padding: 24px 16px;
  display: flex; flex-direction: column; gap: 22px;
  overflow-y: auto;
}
.ds-section { display: flex; flex-direction: column; gap: 2px; }
.ds-section-title {
  font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase;
  color: var(--t3, var(--t-muted)); font-weight: 600;
  margin-bottom: 4px;
  display: flex; align-items: center; gap: 6px;
}
.ds-lock { font-size: 9px; color: var(--t3, var(--t-muted)); font-weight: 500; letter-spacing: 0.04em; text-transform: none; }

.ds-link {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 10px;
  font-size: 12.5px;
  color: var(--t1, #1E2A4A);
  text-decoration: none;
  border-radius: 6px;
  transition: background 120ms, color 120ms;
}
.ds-link:hover { background: rgba(127,119,221,.06); color: var(--p-deep); }
.ds-link.active { background: rgba(127,119,221,.12); color: var(--p-deep); font-weight: 500; }
.ds-link-muted { color: #C8C7C0; }
.ds-count {
  font-size: 9.5px; color: #C8C7C0;
  font-variant-numeric: tabular-nums;
  background: rgba(127,119,221,.04);
  padding: 1px 6px; border-radius: 8px;
}
.ds-login-hint {
  margin-top: 6px;
  font-size: 11px;
  color: var(--t3, var(--t-muted));
  padding: 8px 10px;
  background: rgba(127,119,221,.04);
  border-radius: 6px;
}
.ds-login-hint a { color: var(--p-deep); text-decoration: none; }
.ds-login-hint a:hover { text-decoration: underline; }

@media (max-width: 900px) {
  .ds-side { width: 100%; border-right: none; border-bottom: 0.5px solid #F1EFE8; padding: 14px 18px; flex-direction: row; flex-wrap: wrap; gap: 12px; }
  .ds-section { flex: 1; min-width: 160px; }
}
</style>
