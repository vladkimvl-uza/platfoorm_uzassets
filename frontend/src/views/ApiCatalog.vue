<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api } from "@/api/client";
import BIcon from "@/components/broadcasts/BIcon.vue";
import { apiKeysApi } from "@/api/api_catalog";
import CatalogBrowser from "@/components/api/CatalogBrowser.vue";
import ApiKeysManager from "@/components/api/ApiKeysManager.vue";
import WebhooksManager from "@/components/api/WebhooksManager.vue";
import ExternalApisManager from "@/components/api/ExternalApisManager.vue";
import PartnersManager from "@/components/api/PartnersManager.vue";
import AuditLogView from "@/components/api/AuditLogView.vue";
import CustomApiBuilder from "@/components/api/CustomApiBuilder.vue";

type Tab = "catalog" | "builder" | "keys" | "webhooks" | "external" | "partners" | "audit";
const tab = ref<Tab>("catalog");

const counts = ref<{ total: number; active: number; revoked: number; service_accounts: number } | null>(null);
async function loadCounts() {
  try {
    const r = await apiKeysApi.catalog();
    counts.value = r.counts;
  } catch { /* silent */ }
}
onMounted(loadCounts);

// Скачивание через axios (Authorization-заголовок прикрепляется клиентом) —
// window.open уходил без JWT и мог вернуть 401/403 на защищённом эндпоинте.
async function downloadFile(path: string, filename: string) {
  try {
    const resp = await api.get(path, { responseType: "blob" });
    const url = URL.createObjectURL(resp.data as Blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch { /* ignore download error */ }
}
function downloadOpenApi() { downloadFile("/api-catalog/openapi.enriched.json", "openapi.enriched.json"); }
function downloadPostman() { downloadFile("/api-catalog/postman.json", "postman.json"); }
</script>

<template>
  <div class="ac-page">
    <div class="ac-topbar">
      <div class="ac-tb-l">
        <span class="ac-tb-icn"><BIcon name="api" :size="14" /></span>
        <div>
          <div class="ac-eye">Доступы и интеграции</div>
          <div class="ac-ttl">API &amp; Интеграции</div>
        </div>
      </div>
      <div class="ac-tb-r">
        <button class="ac-tb-btn" @click="downloadOpenApi">
          <BIcon name="file-download" :size="14" /> OpenAPI 3.1
        </button>
        <button class="ac-tb-btn" @click="downloadPostman">
          <BIcon name="download" :size="14" /> Postman
        </button>
      </div>
    </div>

    <div class="ac-subnav">
      <button class="ac-stab" :class="{ active: tab === 'catalog' }" @click="tab = 'catalog'">
        <BIcon name="book-2" :size="14" /> Каталог
      </button>
      <button class="ac-stab" :class="{ active: tab === 'builder' }" @click="tab = 'builder'">
        <BIcon name="terminal-2" :size="14" /> Конструктор
      </button>
      <button class="ac-stab" :class="{ active: tab === 'keys' }" @click="tab = 'keys'">
        <BIcon name="key" :size="14" /> Service accounts &amp; ключи
        <span v-if="counts" class="ac-stab-c">{{ counts.active }}/{{ counts.total }}</span>
      </button>
      <button class="ac-stab" :class="{ active: tab === 'webhooks' }" @click="tab = 'webhooks'">
        <BIcon name="webhook" :size="14" /> Webhooks
      </button>
      <button class="ac-stab" :class="{ active: tab === 'external' }" @click="tab = 'external'">
        <BIcon name="plug" :size="14" /> Внешние API
      </button>
      <button class="ac-stab" :class="{ active: tab === 'partners' }" @click="tab = 'partners'">
        <BIcon name="building-arch" :size="14" /> Партнёры
      </button>
      <button class="ac-stab" :class="{ active: tab === 'audit' }" @click="tab = 'audit'">
        <BIcon name="history" :size="14" /> Журнал
      </button>
    </div>

    <CatalogBrowser v-if="tab === 'catalog'" />
    <CustomApiBuilder v-else-if="tab === 'builder'" />
    <ApiKeysManager v-else-if="tab === 'keys'" @changed="loadCounts" />
    <WebhooksManager v-else-if="tab === 'webhooks'" />
    <ExternalApisManager v-else-if="tab === 'external'" />
    <PartnersManager v-else-if="tab === 'partners'" />
    <AuditLogView v-else-if="tab === 'audit'" />
  </div>
</template>

<style scoped>
.ac-page { display: flex; flex-direction: column; flex: 1; background: var(--color-background-tertiary); min-height: 100%; }

.ac-topbar {
  background: linear-gradient(95deg, #1E2A4A 0%, #2D3760 60%, #4B477E 100%);
  padding: 14px 22px;
  display: flex; justify-content: space-between; align-items: center;
}
.ac-tb-l { display: flex; align-items: center; gap: 11px; }
.ac-tb-icn {
  width: 34px; height: 34px;
  border-radius: 8px;
  background: rgba(127,119,221,.2);
  color: #fff;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 18px;
}
.ac-eye { font-size: 10px; color: rgba(255,255,255,.55); text-transform: uppercase; letter-spacing: .08em; font-weight: 500; }
.ac-ttl { font-size: 16px; color: #fff; font-weight: 500; margin-top: 2px; }
.ac-tb-r { display: flex; gap: 6px; }
.ac-tb-btn {
  background: rgba(255,255,255,.1);
  color: #fff;
  border: 0;
  padding: 7px 12px;
  border-radius: 6px;
  font-size: 11.5px;
  font-weight: 500;
  cursor: pointer;
  display: inline-flex; align-items: center; gap: 5px;
  font-family: inherit;
}
.ac-tb-btn:hover { background: rgba(255,255,255,.18); }

.ac-subnav {
  display: flex;
  padding: 0 18px;
  background: var(--color-background-primary);
  border-bottom: 0.5px solid var(--color-border-tertiary);
}
.ac-stab {
  background: transparent;
  border: 0;
  padding: 10px 14px 12px;
  font-family: inherit;
  font-size: 12px;
  color: var(--color-text-secondary);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  display: inline-flex; align-items: center; gap: 5px;
}
.ac-stab:hover:not(:disabled) { color: var(--color-text-primary); }
.ac-stab:disabled { cursor: not-allowed; opacity: .55; }
.ac-stab.active {
  color: var(--color-text-primary);
  border-bottom-color: #7F77DD;
  font-weight: 500;
}
.ac-stab-c {
  background: rgba(127,119,221,.1);
  color: var(--p-deep);
  padding: 1px 7px;
  border-radius: 9px;
  font-size: 9.5px;
  margin-left: 3px;
  font-feature-settings: "tnum";
}

.ac-stub {
  padding: 80px 40px;
  text-align: center;
  color: var(--color-text-tertiary);
  font-size: 13px;
  display: flex; flex-direction: column; align-items: center; gap: 8px;
}
</style>