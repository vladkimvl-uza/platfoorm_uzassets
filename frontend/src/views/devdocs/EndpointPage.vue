<script setup lang="ts">
/**
 * Endpoint detail page — auto-generated from OpenAPI metadata.
 * Sections: method+path · description · code samples (curl/python/js/go).
 */
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { useApiCatalogStore } from "@/stores/apiCatalog";
import { generateCurl, generatePython, generateJS, generateGo } from "@/utils/codeGenerator";

const route   = useRoute();
const catalog = useApiCatalogStore();
const tab     = ref<"curl" | "python" | "js" | "go">("curl");

onMounted(() => catalog.loadSummary());

const moduleCode = computed(() => String(route.params.module || ""));
const opId       = computed(() => String(route.params.operation || ""));

const endpoint = computed(() => {
  if (!catalog.summary) return null;
  return catalog.summary.endpoints.find(
    e => (e.module || "") === moduleCode.value
      && (e.operation_id === opId.value || (e.method + ":" + e.path).toLowerCase() === opId.value.toLowerCase()),
  ) || null;
});

const code = computed(() => {
  if (!endpoint.value) return "";
  switch (tab.value) {
    case "curl":   return generateCurl(endpoint.value);
    case "python": return generatePython(endpoint.value);
    case "js":     return generateJS(endpoint.value);
    case "go":     return generateGo(endpoint.value);
  }
});

const methodColor = computed(() => {
  const m = endpoint.value?.method.toUpperCase();
  if (m === "GET")    return { bg: "#E1F5EE", fg: "#0F6E56" };
  if (m === "PATCH")  return { bg: "#FAEEDA", fg: "#854F0B" };
  if (m === "POST" || m === "PUT") return { bg: "#E6F1FB", fg: "#0C447C" };
  if (m === "DELETE") return { bg: "#FCEBEB", fg: "#A82C2B" };
  return { bg: "rgba(127,119,221,.15)", fg: "#3C3489" };
});
</script>

<template>
  <article class="ep" v-if="endpoint">
    <header class="ep-head">
      <div class="ep-eyebrow">
        Модуль <RouterLink :to="`/api-docs/endpoints/${moduleCode}`">{{ moduleCode }}</RouterLink>
      </div>
      <h1 class="ep-h1">
        <span class="ep-method" :style="{ background: methodColor.bg, color: methodColor.fg }">
          {{ endpoint.method }}
        </span>
        <code class="ep-path">{{ endpoint.path }}</code>
      </h1>
      <p v-if="endpoint.summary" class="ep-summary">{{ endpoint.summary }}</p>
      <div class="ep-meta">
        <span v-if="endpoint.required_permission" class="ep-perm">
          Право: <code>{{ endpoint.required_permission }}</code>
        </span>
        <span v-if="endpoint.tags?.length" class="ep-tags">
          {{ endpoint.tags.join(" · ") }}
        </span>
      </div>
    </header>

    <p v-if="endpoint.description" class="ep-desc">{{ endpoint.description }}</p>

    <section class="ep-code-section">
      <div class="ep-code-tabs">
        <button v-for="t in (['curl','python','js','go'] as const)" :key="t"
                class="ep-code-tab" :class="{ active: tab === t }"
                @click="tab = t">{{ t === "js" ? "JavaScript" : t.charAt(0).toUpperCase() + t.slice(1) }}</button>
      </div>
      <pre class="ep-code">{{ code }}</pre>
    </section>

    <section class="ep-info">
      <h2 class="ep-h2">Дополнительно</h2>
      <p>Полная схема параметров и ответа доступна в
        <a href="/api/api-catalog/openapi.json" target="_blank">/api-catalog/openapi.json</a>
        — отдельный JSON, который генерируется FastAPI автоматически. Можно использовать
        для codegen клиентов через openapi-generator.
      </p>
    </section>
  </article>

  <div v-else-if="catalog.summary === null" class="ep-loading">Загружаю каталог…</div>
  <div v-else class="ep-empty">Endpoint не найден. <RouterLink to="/api-docs">← На главную</RouterLink></div>
</template>

<style scoped>
.ep { max-width: 760px; }
.ep-eyebrow { font-size: 10.5px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--t3, var(--t-muted)); font-weight: 500; margin-bottom: 6px; }
.ep-eyebrow a { color: var(--p-deep); text-decoration: none; font-family: ui-monospace, Menlo, monospace; }
.ep-eyebrow a:hover { text-decoration: underline; }
.ep-h1 { display: flex; align-items: center; gap: 10px; font-size: 18px; font-weight: 500; margin: 0; flex-wrap: wrap; }
.ep-method { font-size: 11px; font-weight: 600; padding: 3px 9px; border-radius: 6px; letter-spacing: 0.06em; font-family: ui-monospace, Menlo, monospace; }
.ep-path   { font-family: ui-monospace, Menlo, monospace; color: var(--t1, #1E2A4A); font-size: 15px; word-break: break-all; }
.ep-summary { font-size: 14px; color: #444; margin: 10px 0 0 0; line-height: 1.5; }
.ep-meta   { display: flex; gap: 14px; flex-wrap: wrap; margin-top: 10px; font-size: 11.5px; color: var(--t3, var(--t-muted)); }
.ep-perm code { font-family: ui-monospace, Menlo, monospace; background: rgba(127,119,221,.08); color: var(--p-deep); padding: 1px 5px; border-radius: 4px; }
.ep-desc { font-size: 13px; color: #444; line-height: 1.6; margin: 18px 0; }

.ep-code-section { margin: 22px 0; }
.ep-code-tabs { display: flex; gap: 2px; margin-bottom: -1px; }
.ep-code-tab {
  background: transparent; border: 1px solid transparent;
  padding: 6px 14px; border-radius: 8px 8px 0 0;
  font-size: 12px; color: var(--t3, var(--t-muted)); cursor: pointer; font-weight: 500;
  border-bottom: none;
  transition: all 120ms;
}
.ep-code-tab:hover { color: var(--t1, #1E2A4A); }
.ep-code-tab.active { background: #1E2A4A; color: white; border-color: #1E2A4A; }
.ep-code {
  background: #1E2A4A; color: var(--border-input);
  border-radius: 0 10px 10px 10px;
  padding: 16px;
  font-family: ui-monospace, Menlo, monospace;
  font-size: 12px; line-height: 1.55;
  overflow-x: auto;
  margin: 0;
  white-space: pre-wrap; word-wrap: break-word;
}

.ep-info { margin-top: 28px; }
.ep-h2 { font-size: 15px; font-weight: 500; color: var(--t1, #1E2A4A); margin: 0 0 8px 0; }
.ep-info p { font-size: 13px; color: #444; line-height: 1.55; }
.ep-info a { color: var(--p-deep); text-decoration: none; }
.ep-info a:hover { text-decoration: underline; }

.ep-loading, .ep-empty { padding: 32px; text-align: center; color: var(--t3, var(--t-muted)); font-size: 13px; }
.ep-empty a { color: var(--p-deep); text-decoration: none; }
</style>
