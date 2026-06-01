<script setup lang="ts">
/**
 * Full "API · Интеграция" tab — shown when the active library Detail tab
 * has code='api'. Lists ALL company-scoped endpoints with search, method
 * filter, and module group-by.
 */
import { computed, onMounted, ref, watch } from "vue";
import { useApiCatalogStore } from "@/stores/apiCatalog";
import type { CatalogEndpointWithSubstitution, HttpMethod } from "@/api/apiCatalog";
import EndpointCard from "./EndpointCard.vue";

const props = defineProps<{ companyId: string }>();
const emit  = defineEmits<{
  (e: "open-try", endpoint: CatalogEndpointWithSubstitution): void;
}>();

const store = useApiCatalogStore();
const endpoints = ref<CatalogEndpointWithSubstitution[]>([]);
const loading   = ref(false);
const error     = ref<string | null>(null);

const searchQuery  = ref("");
const methodFilter = ref<"all" | HttpMethod>("all");
const groupBy      = ref<"module" | "method" | "none">("module");

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const resp = await store.loadByCompany(props.companyId);
    endpoints.value = resp ? resp.endpoints : [];
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить каталог";
    endpoints.value = [];
  } finally {
    loading.value = false;
  }
}

onMounted(load);
watch(() => props.companyId, load);

const countsByMethod = computed(() => {
  const c: Record<string, number> = { all: endpoints.value.length };
  for (const e of endpoints.value) {
    c[e.method] = (c[e.method] || 0) + 1;
  }
  return c;
});

const filtered = computed(() => {
  let list = endpoints.value;
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase();
    list = list.filter(e =>
      (e.display_path || e.path).toLowerCase().includes(q)
      || (e.summary || "").toLowerCase().includes(q)
      || (e.tags || []).some(t => t.toLowerCase().includes(q)),
    );
  }
  if (methodFilter.value !== "all") {
    list = list.filter(e => e.method === methodFilter.value);
  }
  return list;
});

const grouped = computed<{ name: string; items: CatalogEndpointWithSubstitution[] }[]>(() => {
  if (groupBy.value === "none") return [{ name: "Все", items: filtered.value }];
  const out: Record<string, CatalogEndpointWithSubstitution[]> = {};
  for (const e of filtered.value) {
    const key = groupBy.value === "method"
      ? e.method
      : (e.module || e.tags?.[0] || "Прочее");
    (out[key] ||= []).push(e);
  }
  return Object.entries(out)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([name, items]) => ({ name, items }));
});

const methodOptions: ("all" | HttpMethod)[] = ["all", "GET", "PATCH", "POST", "PUT", "DELETE", "WEBSOCKET"];
</script>

<template>
  <div class="cat-tab">
    <!-- Sticky toolbar -->
    <div class="cat-tool">
      <input
        v-model="searchQuery"
        type="text"
        placeholder="Поиск: financials, kpi, /companies…"
        class="cat-search"
      />
      <div class="cat-methods">
        <button
          v-for="m in methodOptions"
          :key="m"
          class="cat-method-btn"
          :class="{ active: methodFilter === m }"
          @click="methodFilter = m"
        >
          {{ m === "all" ? "Все" : m }}
          <span class="cat-method-cnt">{{ countsByMethod[m] || 0 }}</span>
        </button>
      </div>
      <select v-model="groupBy" class="cat-group">
        <option value="module">Группировка: модуль</option>
        <option value="method">HTTP метод</option>
        <option value="none">Без группировки</option>
      </select>
    </div>

    <div v-if="loading && endpoints.length === 0" class="cat-loading">Загружаю endpoints…</div>
    <div v-else-if="error" class="cat-error">{{ error }}</div>
    <div v-else-if="filtered.length === 0" class="cat-empty">
      По текущим фильтрам нет endpoints
    </div>

    <!-- Grouped lists -->
    <div v-else class="cat-groups">
      <section v-for="g in grouped" :key="g.name" class="cat-group-box">
        <header class="cat-group-h">
          <span class="cat-group-name">{{ g.name }}</span>
          <span class="cat-group-cnt">· {{ g.items.length }} endpoints</span>
        </header>
        <div class="cat-group-items">
          <EndpointCard
            v-for="e in g.items"
            :key="e.method + ':' + e.path"
            :endpoint="e"
            @try="emit('open-try', $event)"
          />
        </div>
      </section>
    </div>

    <!-- Footer legend -->
    <footer class="cat-foot">
      <span class="cat-legend">
        <span class="cat-legend-pill cat-legend-public">public</span> без токена
      </span>
      <span class="cat-legend">
        <span class="cat-legend-pill cat-legend-authed">authed</span> JWT обязателен
      </span>
      <span class="cat-legend">
        <span class="cat-legend-pill cat-legend-admin">admin</span> только owner
      </span>
      <RouterLink to="/api-docs" class="cat-docs-link">Открыть в API-документации →</RouterLink>
    </footer>
  </div>
</template>

<style scoped>
.cat-tab { display: flex; flex-direction: column; gap: 14px; }

/* Sticky toolbar */
.cat-tool {
  position: sticky; top: 0; z-index: 5;
  background: var(--bg2, #FAFAFC);
  padding: 10px 0;
  border-bottom: 0.5px solid #F1EFE8;
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
}
.cat-search {
  flex: 1; min-width: 240px;
  padding: 7px 11px;
  border: 1px solid var(--border-hard);
  border-radius: 8px;
  font-size: 12.5px;
  background: white; color: var(--t1, #1E2A4A);
  outline: none;
}
.cat-search:focus { border-color: #7F77DD; box-shadow: 0 0 0 2px rgba(127,119,221,.15); }

.cat-methods { display: flex; gap: 4px; flex-wrap: wrap; }
.cat-method-btn {
  background: white; border: 1px solid var(--border-hard); color: var(--t1, #1E2A4A);
  padding: 4px 9px; border-radius: 8px;
  font-size: 11px; cursor: pointer; transition: all 120ms;
  display: flex; align-items: center; gap: 5px;
}
.cat-method-btn:hover { background: rgba(127,119,221,.06); border-color: rgba(127,119,221,.4); }
.cat-method-btn.active { background: #7F77DD; color: white; border-color: #7F77DD; }
.cat-method-cnt { font-size: 9.5px; opacity: .75; font-variant-numeric: tabular-nums; }

.cat-group {
  padding: 6px 10px;
  border: 1px solid var(--border-hard);
  border-radius: 8px;
  background: white; color: var(--t1, #1E2A4A);
  font-size: 12px; cursor: pointer;
  outline: none;
}

.cat-loading,
.cat-empty,
.cat-error { padding: 32px; text-align: center; color: var(--t3, var(--t-muted)); font-size: 13px; }
.cat-error { background: rgba(226,75,74,.08); color: #A82C2B; border-radius: 8px; }

.cat-groups { display: flex; flex-direction: column; gap: 20px; }
.cat-group-h {
  display: flex; align-items: baseline; gap: 6px;
  font-size: 10.5px; letter-spacing: 0.06em;
  text-transform: uppercase; color: var(--t3, var(--t-muted)); font-weight: 500;
  margin-bottom: 8px;
}
.cat-group-name { color: var(--t1, #1E2A4A); }
.cat-group-cnt  { color: #C8C7C0; font-weight: 400; text-transform: none; letter-spacing: 0; }

.cat-group-items { display: flex; flex-direction: column; gap: 6px; }

.cat-foot {
  display: flex; gap: 16px; align-items: center;
  padding: 12px 0;
  border-top: 0.5px solid #F1EFE8;
  font-size: 11px; color: var(--t3, var(--t-muted));
  flex-wrap: wrap;
}
.cat-legend { display: flex; align-items: center; gap: 5px; }
.cat-legend-pill { padding: 1px 7px; border-radius: 7px; font-size: 9.5px; font-weight: 500; }
.cat-legend-public { background: rgba(29,158,117,.10); color: #0F6E56; }
.cat-legend-authed { background: rgba(239,159,39,.12); color: #854F0B; }
.cat-legend-admin  { background: rgba(226,75,74,.10); color: #A82C2B; }
.cat-docs-link    { margin-left: auto; color: var(--p-deep); text-decoration: none; font-weight: 500; }
.cat-docs-link:hover { text-decoration: underline; }
</style>
