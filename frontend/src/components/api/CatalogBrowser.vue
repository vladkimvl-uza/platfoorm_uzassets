<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  apiCatalogApi, methodPill,
  type CatalogEndpoint, type CatalogSummary,
} from "@/api/api_catalog";

const summary  = ref<CatalogSummary | null>(null);
const loading  = ref(false);
const error    = ref<string | null>(null);
const selectedModule = ref<string | null>(null);
const searchQ  = ref("");
const methodFilter = ref<string>("ALL");
const expandedKey = ref<string | null>(null);

async function load() {
  loading.value = true;
  error.value = null;
  try { summary.value = await apiCatalogApi.summary(); }
  catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
  finally { loading.value = false; }
}
onMounted(load);

const groupedModules = computed(() => {
  if (!summary.value) return {};
  const out: Record<string, typeof summary.value.modules> = {};
  for (const m of summary.value.modules) {
    const g = m.group || "Прочее";
    (out[g] ??= []).push(m);
  }
  return out;
});

const filteredEndpoints = computed<CatalogEndpoint[]>(() => {
  if (!summary.value) return [];
  let xs = summary.value.endpoints;
  if (selectedModule.value) xs = xs.filter((e) => e.module === selectedModule.value);
  if (methodFilter.value !== "ALL") xs = xs.filter((e) => e.method.toUpperCase() === methodFilter.value);
  if (searchQ.value.trim()) {
    const q = searchQ.value.toLowerCase();
    xs = xs.filter((e) =>
      e.path.toLowerCase().includes(q) ||
      (e.summary || "").toLowerCase().includes(q) ||
      (e.operation_id || "").toLowerCase().includes(q),
    );
  }
  return xs;
});

const moduleBannerEndpoints = computed(() => {
  if (!selectedModule.value || !summary.value) return null;
  const list = summary.value.endpoints.filter((e) => e.module === selectedModule.value);
  return { name: selectedModule.value, count: list.length };
});

function epKey(e: CatalogEndpoint): string {
  return `${e.method}::${e.path}`;
}
function toggleEp(e: CatalogEndpoint) {
  const k = epKey(e);
  expandedKey.value = expandedKey.value === k ? null : k;
}

function curlExample(e: CatalogEndpoint): string {
  const m = e.method.toUpperCase();
  const path = e.path.replace(/{([^}]+)}/g, ":$1");
  const base = "https://platform.uz-assets.uz/api";
  let cmd = `curl -X ${m} ${base}${path} \\\n  -H "Authorization: Bearer $UZA_API_KEY"`;
  if (["POST", "PUT", "PATCH"].includes(m)) {
    cmd += ` \\\n  -H "Content-Type: application/json" \\\n  -d '{}'`;
  }
  return cmd;
}

async function copyCurl(e: CatalogEndpoint) {
  try { await navigator.clipboard.writeText(curlExample(e)); }
  catch { /* silent */ }
}
</script>

<template>
  <div class="cb-wrap">
    <div v-if="error" class="cb-err">{{ error }}</div>

    <div v-if="loading && !summary" class="cb-loading">
      <i class="ti ti-loader-2" style="font-size: 24px;" aria-hidden="true"></i>
      Сканируем endpoints…
    </div>

    <div v-else-if="summary" class="cb-body">

      <div class="cb-side">
        <div class="cb-side-hd">Модули · {{ summary.total_endpoints }} endpoints</div>

        <div class="cb-mod-row" :class="{ active: !selectedModule }" @click="selectedModule = null">
          <span>Все модули</span>
          <span class="cb-mod-c">{{ summary.total_endpoints }}</span>
        </div>

        <div v-for="(modList, group) in groupedModules" :key="group" class="cb-modgrp">
          <div class="cb-modgrp-name">{{ group }}</div>
          <div v-for="m in modList" :key="m.name" class="cb-mod-row"
               :class="{ active: selectedModule === m.name }"
               @click="selectedModule = m.name">
            <span>{{ m.name }}</span>
            <span class="cb-mod-c">{{ m.endpoints_count }}</span>
          </div>
        </div>
      </div>

      <div class="cb-main">
        <div v-if="moduleBannerEndpoints" class="cb-banner">
          <div class="cb-banner-t">{{ moduleBannerEndpoints.name }}</div>
          <div class="cb-banner-s">{{ moduleBannerEndpoints.count }} endpoints</div>
        </div>

        <div class="cb-actbar">
          <div class="cb-search">
            <i class="ti ti-search" aria-hidden="true"></i>
            <input v-model="searchQ" type="text" placeholder="Поиск по пути, описанию, operation_id…"/>
          </div>
          <div class="cb-mpills">
            <button v-for="m in ['ALL','GET','POST','PATCH','DELETE']" :key="m"
                    class="cb-mpill" :class="{ on: methodFilter === m }"
                    @click="methodFilter = m">{{ m }}</button>
          </div>
        </div>

        <div v-if="filteredEndpoints.length === 0" class="cb-empty">
          <i class="ti ti-search-off" style="font-size: 20px; opacity: .4;" aria-hidden="true"></i>
          Ничего не найдено
        </div>

        <div v-else class="cb-eplist">
          <div v-for="e in filteredEndpoints" :key="epKey(e)" class="cb-ep"
               :class="{ open: expandedKey === epKey(e) }">
            <div class="cb-ep-hd" @click="toggleEp(e)">
              <span class="cb-m" :style="{ color: methodPill(e.method).color, background: methodPill(e.method).bg }">
                {{ e.method }}
              </span>
              <span class="cb-path">{{ e.path }}</span>
              <span class="cb-sum">{{ e.summary || "—" }}</span>
              <span v-if="e.required_permission" class="cb-perm" :title="`Требуется permission ${e.required_permission}`">
                {{ e.required_permission }}
              </span>
              <span v-if="e.deprecated" class="cb-dep">deprecated</span>
              <i class="ti" :class="expandedKey === epKey(e) ? 'ti-chevron-up' : 'ti-chevron-down'" aria-hidden="true"></i>
            </div>
            <div v-if="expandedKey === epKey(e)" class="cb-ep-body">
              <div v-if="e.description" class="cb-desc">{{ e.description }}</div>
              <div v-else class="cb-desc cb-desc-empty">Описание отсутствует — добавьте docstring к endpoint функции.</div>

              <div class="cb-sec">
                <div class="cb-sec-hd">Tags</div>
                <div>
                  <span v-for="t in (e.tags.length ? e.tags : ['(нет)'])" :key="t" class="cb-tag">{{ t }}</span>
                </div>
              </div>

              <div class="cb-sec">
                <div class="cb-sec-hd">Пример запроса · curl</div>
                <pre class="cb-code"><span class="cb-code-copy"><button @click="copyCurl(e)"><i class="ti ti-copy" aria-hidden="true"></i> копир.</button></span>{{ curlExample(e) }}</pre>
              </div>

              <div class="cb-actions">
                <button class="cb-btn" disabled title="Pack 12.3">
                  <i class="ti ti-player-play" aria-hidden="true"></i> Try it out
                </button>
                <button class="cb-btn" @click="copyCurl(e)">
                  <i class="ti ti-terminal-2" aria-hidden="true"></i> Скопировать curl
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cb-wrap { flex: 1; display: flex; flex-direction: column; background: var(--color-background-tertiary); }
.cb-err { margin: 8px 18px; padding: 8px 12px; background: rgba(226,75,74,.08); color: #A32D2D; border-radius: 7px; font-size: 11.5px; }
.cb-loading {
  padding: 60px; text-align: center; color: var(--color-text-tertiary); font-size: 13px;
  display: flex; flex-direction: column; align-items: center; gap: 8px;
}

.cb-body {
  display: grid;
  grid-template-columns: 220px 1fr;
  flex: 1;
  min-height: 0;
}

.cb-side {
  border-right: 0.5px solid var(--color-border-tertiary);
  background: var(--color-background-primary);
  padding: 12px 0;
  overflow-y: auto;
}
.cb-side-hd {
  font-size: 9.5px;
  color: var(--color-text-tertiary);
  padding: 0 14px 8px;
  text-transform: uppercase;
  letter-spacing: .07em;
  font-weight: 500;
}
.cb-modgrp { padding: 4px 0 8px; }
.cb-modgrp-name {
  font-size: 10px;
  color: var(--color-text-tertiary);
  padding: 6px 14px 3px;
  text-transform: uppercase;
  letter-spacing: .04em;
}
.cb-mod-row {
  display: flex; justify-content: space-between; align-items: center;
  padding: 5px 14px;
  cursor: pointer;
  font-size: 11.5px;
  color: var(--color-text-secondary);
  position: relative;
  overflow: hidden;
}
.cb-mod-row:hover { background: rgba(127,119,221,.04); }
.cb-mod-row.active {
  background: rgba(127,119,221,.08);
  color: var(--color-text-primary);
  font-weight: 500;
}
.cb-mod-row.active::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 2px; background: #7F77DD;
  animation: uzaStripeDrawIn .4s cubic-bezier(0.34, 1.2, 0.64, 1) both;
  transform-origin: left center;
  pointer-events: none;
}
.cb-mod-c {
  background: rgba(0,0,0,.05);
  color: var(--color-text-secondary);
  padding: 1px 6px;
  border-radius: 8px;
  font-size: 9px;
  font-feature-settings: "tnum";
}

.cb-main {
  padding: 12px 18px;
  overflow-y: auto;
}

.cb-banner {
  background: linear-gradient(90deg, rgba(127,119,221,.06), transparent);
  padding: 9px 13px;
  margin-bottom: 10px;
  border-radius: 6px;
  position: relative; overflow: hidden;
}
.cb-banner::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; background: #7F77DD;
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  animation:
    uzaStripeDrawIn .8s cubic-bezier(0.34, 1.2, 0.64, 1) 100ms both,
    uzaStripeBreathe 2.8s ease-in-out 1s infinite;
  pointer-events: none;
}
.cb-banner-t { font-size: 13px; color: var(--color-text-primary); font-weight: 500; }
.cb-banner-s { font-size: 10.5px; color: var(--color-text-tertiary); margin-top: 2px; }

.cb-actbar { display: flex; gap: 6px; margin-bottom: 12px; }
.cb-search { flex: 1; position: relative; }
.cb-search input {
  width: 100%;
  padding: 7px 11px 7px 30px;
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: 6px;
  font-size: 12px;
  font-family: inherit;
  outline: none;
  background: var(--color-background-primary);
}
.cb-search i { position: absolute; left: 10px; top: 8px; color: var(--color-text-tertiary); font-size: 13px; }

.cb-mpills { display: flex; gap: 3px; }
.cb-mpill {
  background: var(--color-background-secondary);
  border: 0.5px solid rgba(0,0,0,.06);
  color: var(--color-text-secondary);
  padding: 4px 10px;
  border-radius: 5px;
  font-size: 10px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
}
.cb-mpill.on { background: #7F77DD; color: #fff; border-color: #7F77DD; }

.cb-empty {
  padding: 50px;
  text-align: center;
  color: var(--color-text-tertiary);
  font-size: 11.5px;
  display: flex; flex-direction: column; align-items: center; gap: 6px;
}

.cb-eplist { display: flex; flex-direction: column; gap: 5px; }
.cb-ep {
  background: var(--color-background-primary);
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: 7px;
  overflow: hidden;
}
.cb-ep.open { border-color: rgba(127,119,221,.4); }

.cb-ep-hd {
  display: flex; align-items: center; gap: 9px;
  padding: 7px 11px;
  cursor: pointer;
}
.cb-ep-hd:hover { background: rgba(0,0,0,.015); }
.cb-ep.open .cb-ep-hd { background: rgba(127,119,221,.04); }

.cb-m {
  padding: 2px 7px;
  border-radius: 4px;
  font-size: 9.5px;
  font-weight: 600;
  font-family: var(--font-mono, monospace);
  min-width: 52px;
  text-align: center;
}
.cb-path {
  font-family: var(--font-mono, monospace);
  font-size: 11.5px;
  color: var(--color-text-primary);
  flex: 0 0 auto;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 45%;
}
.cb-sum {
  font-size: 11px;
  color: var(--color-text-secondary);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cb-perm {
  background: rgba(212,83,126,.1);
  color: #993556;
  padding: 1px 7px;
  border-radius: 3px;
  font-size: 9px;
  font-weight: 500;
  font-family: var(--font-mono, monospace);
}
.cb-dep {
  background: rgba(239,159,39,.15);
  color: #854F0B;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 9px;
  font-weight: 600;
}

.cb-ep-body {
  padding: 12px 14px;
  background: var(--bg2, #FAFAFC);
  border-top: 0.5px solid var(--color-border-tertiary);
}
.cb-desc {
  font-size: 11.5px;
  color: var(--color-text-secondary);
  line-height: 1.55;
  margin-bottom: 10px;
}
.cb-desc-empty { color: var(--color-text-tertiary); font-style: italic; }

.cb-sec { margin-bottom: 10px; }
.cb-sec-hd {
  font-size: 9.5px;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: .06em;
  font-weight: 500;
  margin-bottom: 4px;
}
.cb-tag {
  background: rgba(127,119,221,.08);
  color: #534AB7;
  padding: 2px 8px;
  border-radius: 9px;
  font-size: 10px;
  margin-right: 3px;
}

.cb-code {
  background: #1E2A4A;
  color: #C9D1E0;
  padding: 10px 12px;
  border-radius: 6px;
  font-family: var(--font-mono, monospace);
  font-size: 10.5px;
  line-height: 1.55;
  white-space: pre;
  overflow-x: auto;
  position: relative;
  margin: 0;
}
.cb-code-copy { position: absolute; top: 5px; right: 5px; }
.cb-code-copy button {
  background: rgba(255,255,255,.1);
  color: #fff;
  border: 0;
  padding: 2px 7px;
  border-radius: 3px;
  font-size: 9px;
  cursor: pointer;
  font-family: inherit;
  display: inline-flex; align-items: center; gap: 3px;
}
.cb-code-copy button:hover { background: rgba(255,255,255,.18); }

.cb-actions { display: flex; gap: 5px; margin-top: 8px; }
.cb-btn {
  background: var(--color-background-primary);
  border: 0.5px solid var(--color-border-tertiary);
  padding: 5px 11px;
  border-radius: 5px;
  font-size: 11px;
  font-family: inherit;
  cursor: pointer;
  color: var(--color-text-secondary);
  display: inline-flex; align-items: center; gap: 4px;
}
.cb-btn:disabled { opacity: .55; cursor: not-allowed; }
.cb-btn:hover:not(:disabled) { background: rgba(127,119,221,.04); }
</style>
