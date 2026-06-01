<script setup lang="ts">
/**
 * Public Developer Docs — top-level layout (Phase 5.5).
 * Public — no auth required to view. Try-it-out for non-public endpoints
 * does require auth, but reading the catalog/quickstart is open.
 */
import { computed, onMounted } from "vue";
import { useRoute } from "vue-router";
import { useApiCatalogStore } from "@/stores/apiCatalog";
import DevDocsHero from "./DevDocsHero.vue";
import DevDocsSidebar from "./DevDocsSidebar.vue";
import DevDocsFooter from "./DevDocsFooter.vue";

const route   = useRoute();
const catalog = useApiCatalogStore();

onMounted(async () => {
  await catalog.loadSummary();
});

const showHero = computed(() => route.name === "devdocs-quickstart");
</script>

<template>
  <div class="dd-root">
    <DevDocsHero v-if="showHero" />

    <div class="dd-body">
      <DevDocsSidebar />
      <main class="dd-main">
        <RouterView />
      </main>
    </div>

    <DevDocsFooter />
  </div>
</template>

<style scoped>
.dd-root {
  display: flex; flex-direction: column;
  min-height: 100vh;
  background: var(--bg2, #FAFAFC);
  color: var(--t1, #1E2A4A);
}
.dd-body {
  display: flex;
  flex: 1;
  min-height: 0;
}
.dd-main {
  flex: 1;
  padding: 28px 36px;
  overflow-y: auto;
  max-width: 980px;
}
@media (max-width: 900px) {
  .dd-body { flex-direction: column; }
  .dd-main { padding: 16px; }
}
</style>
