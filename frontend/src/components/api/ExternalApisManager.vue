<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import BIcon from "@/components/broadcasts/BIcon.vue";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import ModalShell from "@/components/ModalShell.vue";
import {
  externalApis, statusPill, AUTH_LABELS,
  type AuthKind, type EnvKind, type ExternalApi, type ExtCatalogSummary, type ExtEndpoint, type ExtStatus,
} from "@/api/external_apis";
import { methodPill } from "@/api/api_catalog";
import { useConfirm } from "@/composables/useConfirm";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();


const { confirmDialog } = useConfirm();

const apis      = ref<ExternalApi[]>([]);
const selected  = ref<ExternalApi | null>(null);
const catalog   = ref<ExtCatalogSummary | null>(null);
const loading   = ref(false);
const error     = ref<string | null>(null);
const searchQ   = ref("");
const filterStatus = ref<ExtStatus | "">("");

const showCreate = ref(false);
const newApi = ref<{
  slug: string; name: string; description: string;
  base_url: string; documentation_url: string; health_check_url: string;
  status: ExtStatus;
  auth_kind: AuthKind;
  environment_kind: EnvKind | "";
  tags: string;
  notes: string;
}>({
  slug: "", name: "", description: "",
  base_url: "https://", documentation_url: "", health_check_url: "",
  status: "active", auth_kind: "none",
  environment_kind: "production", tags: "",
  notes: "",
});

const showSpecUpload = ref(false);
const specText = ref("");
const showDelete = ref<ExternalApi | null>(null);
const endpointFilter = ref({ method: "ALL", q: "" });
const expandedEp = ref<string | null>(null);

async function loadList() {
  loading.value = true; error.value = null;
  try {
    const r = await externalApis.list(searchQ.value || undefined, filterStatus.value || undefined);
    apis.value = r.items;
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
  finally { loading.value = false; }
}

let searchT: ReturnType<typeof setTimeout>;
function onSearch() {
  clearTimeout(searchT);
  searchT = setTimeout(loadList, 300);
}

async function selectApi(a: ExternalApi) {
  selected.value = a;
  catalog.value = null;
  expandedEp.value = null;
  if (a.has_openapi_spec) {
    try { catalog.value = await externalApis.catalog(a.id); }
    catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
  }
}

onMounted(loadList);

async function submitCreate() {
  if (!newApi.value.slug || !newApi.value.name) { error.value = "Заполните slug и name"; return; }
  try {
    const created = await externalApis.create({
      slug: newApi.value.slug.trim(),
      name: newApi.value.name.trim(),
      description: newApi.value.description.trim() || null,
      base_url: newApi.value.base_url.trim(),
      documentation_url: newApi.value.documentation_url.trim() || null,
      health_check_url:  newApi.value.health_check_url.trim() || null,
      status: newApi.value.status,
      auth_kind: newApi.value.auth_kind,
      environment_kind: newApi.value.environment_kind || null,
      tags: newApi.value.tags.split(",").map((s) => s.trim()).filter(Boolean),
      notes: newApi.value.notes.trim() || null,
    });
    showCreate.value = false;
    newApi.value = {
      slug: "", name: "", description: "",
      base_url: "https://", documentation_url: "", health_check_url: "",
      status: "active", auth_kind: "none",
      environment_kind: "production", tags: "", notes: "",
    };
    await loadList();
    await selectApi(created);
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
}

async function uploadSpec() {
  if (!selected.value) return;
  try {
    const parsed = JSON.parse(specText.value);
    await externalApis.uploadSpec(selected.value.id, parsed);
    showSpecUpload.value = false;
    specText.value = "";
    await loadList();
    const refreshed = apis.value.find((a) => a.id === selected.value!.id);
    if (refreshed) await selectApi(refreshed);
  } catch (e: any) {
    if (e instanceof SyntaxError) {
      error.value = "Неверный JSON: " + e.message;
    } else {
      error.value = e?.response?.data?.detail || e?.message;
    }
  }
}

async function removeSpec() {
  if (!selected.value) return;
  if (!(await confirmDialog({ message: `Удалить загруженный OpenAPI спецификацию (${selected.value.endpoint_count} endpoints)?`, danger: true }))) return;
  try {
    await externalApis.removeSpec(selected.value.id);
    catalog.value = null;
    await loadList();
    const refreshed = apis.value.find((a) => a.id === selected.value!.id);
    if (refreshed) await selectApi(refreshed);
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
}

async function confirmDelete() {
  if (!showDelete.value) return;
  try {
    await externalApis.remove(showDelete.value.id);
    if (selected.value?.id === showDelete.value.id) { selected.value = null; catalog.value = null; }
    showDelete.value = null;
    await loadList();
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
}

const filteredEndpoints = computed<ExtEndpoint[]>(() => {
  if (!catalog.value) return [];
  let xs = catalog.value.endpoints;
  if (endpointFilter.value.method !== "ALL") {
    xs = xs.filter((e) => e.method === endpointFilter.value.method);
  }
  if (endpointFilter.value.q.trim()) {
    const q = endpointFilter.value.q.toLowerCase();
    xs = xs.filter((e) =>
      e.path.toLowerCase().includes(q) ||
      (e.summary || "").toLowerCase().includes(q),
    );
  }
  return xs;
});

function epKey(e: ExtEndpoint): string { return `${e.method}::${e.path}`; }
function toggleEp(e: ExtEndpoint) { const k = epKey(e); expandedEp.value = expandedEp.value === k ? null : k; }

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("ru-RU", { day: "numeric", month: "short", year: "numeric" });
}

function pasteSpec() {
  navigator.clipboard.readText().then((t) => { specText.value = t; }).catch(() => {});
}
</script>

<template>
  <div class="xa-wrap">
    <UzaStateBlock v-if="error" state="error" variant="banner" :text="error" dismissible @dismiss="error = null" />

    <div class="xa-body">

      <!-- Left: list -->
      <div class="xa-side">
        <div class="xa-side-hd">
          <div class="xa-side-t">{{ t('Внешние API') }}</div>
          <button class="xa-add" @click="showCreate = true">
            <BIcon name="plus" :size="14" />
          </button>
        </div>
        <div class="xa-side-filter">
          <input v-model="searchQ" @input="onSearch" :placeholder="t('Поиск…')" class="xa-filt-i"/>
          <select v-model="filterStatus" @change="loadList" class="xa-filt-s">
            <option value="">{{ t('все') }}</option>
            <option value="active">active</option>
            <option value="sandbox">sandbox</option>
            <option value="deprecated">deprec.</option>
            <option value="disabled">disabled</option>
          </select>
        </div>

        <UzaStateBlock v-if="!apis.length" state="empty" variant="block" :title="t('Нет внешних API')" desc="Создайте первую запись">
          <template #icon><BIcon name="plug" :size="14" /></template>
        </UzaStateBlock>

        <div v-else class="xa-list">
          <div v-for="a in apis" :key="a.id" class="xa-row"
               :class="{ active: selected?.id === a.id }"
               @click="selectApi(a)"
               :style="{ '--stripe-color': statusPill(a.status).color }">
            <span class="uza-stripe-el" :style="{ '--stripe-color': statusPill(a.status).color }" />
            <div class="xa-row-t">{{ a.name }}</div>
            <div class="xa-row-slug"><code>{{ a.slug }}</code></div>
            <div class="xa-row-meta">
              <span class="xa-pill" :style="{ color: statusPill(a.status).color, background: statusPill(a.status).bg }">
                {{ statusPill(a.status).label }}
              </span>
              <span v-if="a.has_openapi_spec" class="xa-spec-chip">
                <BIcon name="file-code" :size="14" /> {{ a.endpoint_count }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Right: detail -->
      <div class="xa-main">
        <template v-if="selected">
          <div class="xa-hero">
            <div>
              <div class="xa-hero-eye">
                <code class="xa-slug">{{ selected.slug }}</code>
                <span class="xa-pill" :style="{ color: statusPill(selected.status).color, background: statusPill(selected.status).bg }">
                  {{ statusPill(selected.status).label }}
                </span>
                <span v-if="selected.environment_kind" class="xa-env">{{ selected.environment_kind }}</span>
              </div>
              <div class="xa-hero-t">{{ selected.name }}</div>
              <div v-if="selected.description" class="xa-hero-d">{{ selected.description }}</div>
            </div>
            <div class="xa-hero-actions">
              <button v-if="!selected.has_openapi_spec" class="xa-btn xa-btn-primary" @click="showSpecUpload = true">
                <BIcon name="upload" :size="14" /> {{ t('Загрузить OpenAPI') }}
              </button>
              <a v-if="selected.has_openapi_spec" :href="externalApis.downloadUrl(selected.id)" target="_blank" class="xa-btn">
                <BIcon name="download" :size="14" /> {{ t('Скачать spec') }}
              </a>
              <button v-if="selected.has_openapi_spec" class="xa-btn" @click="removeSpec" :title="t('Удалить spec')">
                <BIcon name="trash" :size="14" />
              </button>
              <button class="xa-btn xa-btn-danger" @click="showDelete = selected" :title="t('Удалить API')">
                <BIcon name="x" :size="14" />
              </button>
            </div>
          </div>

          <div class="xa-grid">
            <div class="xa-card">
              <div class="xa-card-hd">{{ t('Подключение') }}</div>
              <div class="xa-kv">
                <div><span>Base URL</span><code>{{ selected.base_url }}</code></div>
                <div v-if="selected.documentation_url">
                  <span>{{ t('Документация') }}</span>
                  <a :href="selected.documentation_url" target="_blank">{{ selected.documentation_url }}</a>
                </div>
                <div v-if="selected.health_check_url">
                  <span>Health check</span>
                  <code>{{ selected.health_check_url }}</code>
                </div>
                <div>
                  <span>{{ t('Авторизация') }}</span>
                  <code>{{ AUTH_LABELS[selected.auth_kind || "none"] }}</code>
                </div>
              </div>
            </div>

            <div class="xa-card">
              <div class="xa-card-hd">{{ t('Метаданные') }}</div>
              <div class="xa-kv">
                <div v-if="selected.tags && selected.tags.length">
                  <span>Tags</span>
                  <div>
                    <span v-for="t in selected.tags" :key="t" class="xa-tag">{{ t }}</span>
                  </div>
                </div>
                <div v-if="selected.openapi_uploaded_at">
                  <span>{{ t('Spec загружен') }}</span>
                  <span>{{ fmtDate(selected.openapi_uploaded_at) }} ({{ selected.openapi_spec_version }})</span>
                </div>
                <div>
                  <span>{{ t('Изменён') }}</span><span>{{ fmtDate(selected.updated_at) }}</span>
                </div>
              </div>
            </div>
          </div>

          <div v-if="selected.notes" class="xa-notes">
            <div class="xa-card-hd">{{ t('Заметки / runbook') }}</div>
            <pre>{{ selected.notes }}</pre>
          </div>

          <!-- ────── OpenAPI catalog ────── -->
          <div v-if="catalog" class="xa-cat">
            <div class="xa-cat-banner">
              <div>
                <div class="xa-cat-t">{{ catalog.title }} <span style="color: var(--color-text-tertiary); font-size: 11px;">v{{ catalog.version }}</span></div>
                <div class="xa-cat-s">{{ catalog.total_endpoints }} endpoints · {{ catalog.servers.length }} server{{ catalog.servers.length === 1 ? "" : "s" }}</div>
              </div>
            </div>

            <div class="xa-cat-filters">
              <input v-model="endpointFilter.q" :placeholder="t('Поиск endpoint…')" class="xa-filt-i"/>
              <div class="xa-mpills">
                <button v-for="m in ['ALL','GET','POST','PATCH','PUT','DELETE']" :key="m"
                        class="xa-mpill" :class="{ on: endpointFilter.method === m }"
                        @click="endpointFilter.method = m">{{ m }}</button>
              </div>
            </div>

            <UzaStateBlock v-if="!filteredEndpoints.length" state="empty" variant="block" text="Ничего не найдено">
              <template #icon><BIcon name="search-off" :size="14" /></template>
            </UzaStateBlock>
            <div v-else class="xa-ep-list">
              <div v-for="e in filteredEndpoints" :key="epKey(e)" class="xa-ep"
                   :class="{ open: expandedEp === epKey(e) }">
                <div class="xa-ep-hd" @click="toggleEp(e)">
                  <span class="xa-m" :style="{ color: methodPill(e.method).color, background: methodPill(e.method).bg }">
                    {{ e.method }}
                  </span>
                  <span class="xa-path">{{ e.path }}</span>
                  <span class="xa-sum">{{ e.summary || "—" }}</span>
                  <span v-if="e.deprecated" class="xa-dep">deprecated</span>
                </div>
                <div v-if="expandedEp === epKey(e)" class="xa-ep-body">
                  <p v-if="e.description">{{ e.description }}</p>
                  <p v-else style="color: var(--color-text-tertiary); font-style: italic;">{{ t('Описание не задано в спецификации') }}</p>
                  <div v-if="e.tags.length">
                    <span class="xa-card-hd" style="display: inline-block; margin-right: 6px;">Tags:</span>
                    <span v-for="t in e.tags" :key="t" class="xa-tag">{{ t }}</span>
                  </div>
                  <div v-if="e.operation_id" style="font-size: 10.5px; color: var(--color-text-tertiary); margin-top: 5px;">
                    operationId: <code>{{ e.operation_id }}</code>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div v-else-if="!selected.has_openapi_spec" class="xa-no-spec">
            <BIcon name="file-off" :size="14" />
            <div>{{ t('OpenAPI спецификация ещё не загружена') }}</div>
            <button class="xa-btn xa-btn-primary" @click="showSpecUpload = true" style="margin-top: 8px;">
              <BIcon name="upload" :size="14" /> {{ t('Загрузить') }}
            </button>
          </div>
        </template>

        <UzaStateBlock v-else state="empty" variant="block" text="Выберите внешний API слева или создайте новый">
          <template #icon><BIcon name="arrow-left" :size="14" /></template>
        </UzaStateBlock>
      </div>
    </div>

    <!-- ───── Modal: create ───── -->
    <ModalShell :open="showCreate" size="lg" :title="t('Новый внешний API')" @close="showCreate = false">
        <div class="xa-modal-body">
          <div class="xa-mgrid">
            <div class="xa-field">
              <label>{{ t('Slug (идентификатор)') }}</label>
              <input v-model="newApi.slug" placeholder="openinfo, sap_erp, cbu_rates"/>
            </div>
            <div class="xa-field">
              <label>{{ t('Имя') }}</label>
              <input v-model="newApi.name" :placeholder="t('openinfo.uz · публичные раскрытия')"/>
            </div>
          </div>
          <div class="xa-field">
            <label>{{ t('Описание') }}</label>
            <textarea v-model="newApi.description" rows="2" :placeholder="t('Источник IFRS отчётности портфельных компаний')"></textarea>
          </div>
          <div class="xa-field">
            <label>Base URL</label>
            <input v-model="newApi.base_url" placeholder="https://api.example.uz/v1"/>
          </div>
          <div class="xa-mgrid">
            <div class="xa-field">
              <label>{{ t('Документация (URL)') }}</label>
              <input v-model="newApi.documentation_url" placeholder="https://docs.example.uz"/>
            </div>
            <div class="xa-field">
              <label>Health check (URL)</label>
              <input v-model="newApi.health_check_url" placeholder="https://api.example.uz/healthz"/>
            </div>
          </div>
          <div class="xa-mgrid" style="grid-template-columns: 1fr 1fr 1fr;">
            <div class="xa-field">
              <label>{{ t('Статус') }}</label>
              <select v-model="newApi.status">
                <option value="active">active</option>
                <option value="sandbox">sandbox</option>
                <option value="deprecated">deprecated</option>
                <option value="disabled">disabled</option>
              </select>
            </div>
            <div class="xa-field">
              <label>{{ t('Окружение') }}</label>
              <select v-model="newApi.environment_kind">
                <option value="production">production</option>
                <option value="sandbox">sandbox</option>
                <option value="on-prem">on-prem</option>
              </select>
            </div>
            <div class="xa-field">
              <label>{{ t('Авторизация') }}</label>
              <select v-model="newApi.auth_kind">
                <option value="none">{{ t('Нет') }}</option>
                <option value="api_key">API key</option>
                <option value="oauth2">OAuth 2.0</option>
                <option value="basic">Basic</option>
                <option value="jwt">JWT</option>
                <option value="mtls">mTLS</option>
              </select>
            </div>
          </div>
          <div class="xa-field">
            <label>{{ t('Tags (через запятую)') }}</label>
            <input v-model="newApi.tags" placeholder="finance, government, weekly"/>
          </div>
          <div class="xa-field">
            <label>{{ t('Заметки') }}</label>
            <textarea v-model="newApi.notes" rows="2" :placeholder="t('Особенности интеграции, ответственный, …')"></textarea>
          </div>
        </div>
      <template #footer>
        <button class="xa-btn xa-btn-ghost" @click="showCreate = false">{{ t('Отмена') }}</button>
        <button class="xa-btn xa-btn-primary" @click="submitCreate">{{ t('Создать') }}</button>
      </template>
    </ModalShell>

    <!-- ───── Modal: upload spec ───── -->
    <ModalShell :open="showSpecUpload" size="xl"
                :title="'Загрузить OpenAPI спецификацию для ' + (selected?.name || '')"
                @close="showSpecUpload = false">
        <div class="xa-modal-body">
          <div style="font-size: 11.5px; color: var(--color-text-secondary); margin-bottom: 8px;">
            {{ t('Вставьте JSON OpenAPI 3.x документа (или Swagger 2.0). Спецификация хранится локально, не запрашивается у источника.') }}
          </div>
          <div class="xa-field">
            <label style="display: flex; justify-content: space-between; align-items: center;">
              <span>OpenAPI JSON</span>
              <button class="xa-btn" style="padding: 3px 9px; font-size: 10.5px;" @click="pasteSpec">
                <BIcon name="clipboard" :size="14" /> {{ t('Вставить из буфера') }}
              </button>
            </label>
            <textarea v-model="specText" rows="14" style="font-family: var(--font-mono, monospace); font-size: 10.5px;" placeholder='{"openapi":"3.0.3","info":{"title":"...","version":"1.0"},"paths":{...}}'></textarea>
          </div>
        </div>
      <template #footer>
        <button class="xa-btn xa-btn-ghost" @click="showSpecUpload = false; specText = ''">{{ t('Отмена') }}</button>
        <button class="xa-btn xa-btn-primary" :disabled="!specText.trim()" @click="uploadSpec">
          <BIcon name="upload" :size="14" /> {{ t('Загрузить') }}
        </button>
      </template>
    </ModalShell>

    <!-- ───── Modal: delete ───── -->
    <ModalShell :open="!!showDelete" size="sm" @close="showDelete = null">
      <template v-if="showDelete" #header>
        <h2 style="margin:0; font-size:15px; font-weight:500; color:#A32D2D;">{{ t('Удалить "') }}{{ showDelete.name }}"?</h2>
      </template>
      <div class="xa-modal-body" v-if="showDelete">
          <div style="font-size: 11.5px; color: var(--color-text-secondary);">
            {{ t('Запись и загруженный OpenAPI будут удалены. Webhook-подписки и API-ключи не затрагиваются.') }}
          </div>
        </div>
      <template #footer>
        <button class="xa-btn xa-btn-ghost" @click="showDelete = null">{{ t('Отмена') }}</button>
        <button class="xa-btn xa-btn-danger" @click="confirmDelete">{{ t('Удалить') }}</button>
      </template>
    </ModalShell>

  </div>
</template>

<style scoped>
.xa-wrap { flex: 1; display: flex; flex-direction: column; background: var(--color-background-tertiary); }

.xa-body { display: grid; grid-template-columns: 280px 1fr; flex: 1; min-height: 0; }

.xa-side { background: var(--color-background-primary); border-right: 0.5px solid var(--color-border-tertiary); overflow-y: auto; display: flex; flex-direction: column; }
.xa-side-hd { padding: 12px 14px 8px; display: flex; justify-content: space-between; align-items: center; }
.xa-side-t { font-size: 12px; color: var(--color-text-primary); font-weight: 500; }
.xa-add { background: rgba(127,119,221,.1); color: var(--p-deep); border: 0; padding: 4px 9px; border-radius: 5px; font-size: 10.5px; cursor: pointer; font-family: inherit; display: inline-flex; align-items: center; gap: 3px; }
.xa-add:hover { background: rgba(127,119,221,.2); }
.xa-side-filter { display: flex; gap: 5px; padding: 0 14px 8px; }
.xa-filt-i, .xa-filt-s { padding: 5px 9px; border: 0.5px solid var(--color-border-tertiary); border-radius: 5px; font-size: 11px; font-family: inherit; outline: none; }
.xa-filt-i { flex: 1; }

.xa-list { display: flex; flex-direction: column; }
.xa-row { padding: 10px 14px 10px 18px; cursor: pointer; border-bottom: 0.5px solid rgba(0,0,0,.04); position: relative; overflow: hidden; }
.xa-row:hover { background: rgba(127,119,221,.04); }
.xa-row.active { background: rgba(127,119,221,.08); }
.xa-row.active::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 2px; background: #7F77DD;
  animation: uzaStripeDrawIn .4s var(--ease-standard) both;
  transform-origin: left center;
  pointer-events: none;
}
.xa-row-t { font-size: 12px; font-weight: 500; color: var(--color-text-primary); }
.xa-row-slug { font-size: 9.5px; color: var(--color-text-tertiary); margin-top: 1px; }
.xa-row-slug code { font-family: var(--font-mono, monospace); }
.xa-row-meta { display: flex; gap: 5px; margin-top: 5px; align-items: center; }

.xa-pill { padding: 2px 7px; border-radius: 4px; font-size: 9.5px; font-weight: 600; text-transform: lowercase; }
.xa-env { background: rgba(0,0,0,.05); color: var(--color-text-secondary); padding: 2px 6px; border-radius: 4px; font-size: 9.5px; }
.xa-spec-chip { background: rgba(127,119,221,.08); color: var(--p-deep); padding: 1px 6px; border-radius: 3px; font-size: 9.5px; display: inline-flex; align-items: center; gap: 2px; font-feature-settings: "tnum"; }

.xa-main { padding: 16px 22px; overflow-y: auto; }

.xa-hero { display: flex; justify-content: space-between; align-items: flex-start; gap: 14px; padding: 14px 16px; background: linear-gradient(90deg, rgba(127,119,221,.06), transparent); border-radius: 7px; margin-bottom: 14px; position: relative; overflow: hidden; }
.xa-hero::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; background: #7F77DD;
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  animation:
    uzaStripeDrawIn .8s var(--ease-standard) 100ms both,
    uzaStripeBreathe 2.8s ease-in-out 1s infinite;
  pointer-events: none;
}
.xa-hero-eye { display: flex; gap: 7px; align-items: center; flex-wrap: wrap; }
.xa-slug { font-family: var(--font-mono, monospace); font-size: 10.5px; background: rgba(0,0,0,.05); padding: 2px 7px; border-radius: 4px; color: var(--color-text-secondary); }
.xa-hero-t { font-size: 16px; font-weight: 500; color: var(--color-text-primary); margin-top: 5px; }
.xa-hero-d { font-size: 11.5px; color: var(--color-text-secondary); margin-top: 3px; line-height: 1.5; }
.xa-hero-actions { display: flex; gap: 5px; flex-shrink: 0; }

.xa-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 14px; }
.xa-card { background: var(--color-background-primary); border: 0.5px solid var(--color-border-tertiary); border-radius: 7px; padding: 11px 14px; }
.xa-card-hd { font-size: 9.5px; color: var(--color-text-tertiary); text-transform: uppercase; letter-spacing: .06em; font-weight: 500; margin-bottom: 7px; }
.xa-kv { display: flex; flex-direction: column; gap: 5px; }
.xa-kv > div { display: flex; gap: 9px; align-items: baseline; font-size: 11.5px; }
.xa-kv > div > span:first-child { color: var(--color-text-tertiary); font-size: 9.5px; text-transform: uppercase; letter-spacing: .04em; min-width: 100px; flex-shrink: 0; }
.xa-kv code, .xa-kv a { font-family: var(--font-mono, monospace); font-size: 10.5px; }
.xa-kv a { color: var(--p-deep); text-decoration: none; word-break: break-all; }
.xa-kv a:hover { text-decoration: underline; }

.xa-tag { background: rgba(127,119,221,.08); color: var(--p-deep); padding: 1px 7px; border-radius: 9px; font-size: 9.5px; margin-right: 3px; display: inline-block; }

.xa-notes { background: var(--bg2, #FAFAFC); border: 0.5px solid var(--color-border-tertiary); border-radius: 7px; padding: 11px 14px; margin-bottom: 14px; }
.xa-notes pre { font-family: inherit; white-space: pre-wrap; font-size: 11.5px; color: var(--color-text-secondary); margin: 0; line-height: 1.5; }

.xa-cat { background: var(--color-background-primary); border: 0.5px solid var(--color-border-tertiary); border-radius: 7px; padding: 12px; }
.xa-cat-banner { background: linear-gradient(90deg, rgba(29,158,117,.06), transparent); padding: 9px 13px; border-radius: 5px; margin-bottom: 10px; position: relative; overflow: hidden; }
.xa-cat-banner::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; background: var(--green);
  animation: uzaStripeDrawIn .6s var(--ease-standard) both;
  transform-origin: left center;
  pointer-events: none;
}
.xa-cat-t { font-size: 13px; color: var(--color-text-primary); font-weight: 500; }
.xa-cat-s { font-size: 10.5px; color: var(--color-text-tertiary); margin-top: 2px; }

.xa-cat-filters { display: flex; gap: 6px; margin-bottom: 9px; }
.xa-cat-filters .xa-filt-i { flex: 1; }
.xa-mpills { display: flex; gap: 3px; }
.xa-mpill { background: var(--color-background-secondary); border: 0.5px solid rgba(0,0,0,.06); color: var(--color-text-secondary); padding: 4px 9px; border-radius: 5px; font-size: 10px; font-weight: 600; cursor: pointer; font-family: inherit; }
.xa-mpill.on { background: #7F77DD; color: #fff; border-color: #7F77DD; }

.xa-ep-list { display: flex; flex-direction: column; gap: 4px; }
.xa-ep { background: var(--bg2, #FAFAFC); border: 0.5px solid var(--color-border-tertiary); border-radius: 6px; overflow: hidden; }
.xa-ep.open { border-color: rgba(127,119,221,.4); background: var(--color-background-primary); }
.xa-ep-hd { display: flex; align-items: center; gap: 9px; padding: 7px 11px; cursor: pointer; }
.xa-ep-hd:hover { background: rgba(127,119,221,.03); }
.xa-m { padding: 2px 7px; border-radius: 4px; font-size: 9.5px; font-weight: 600; font-family: var(--font-mono, monospace); min-width: 52px; text-align: center; }
.xa-path { font-family: var(--font-mono, monospace); font-size: 11.5px; color: var(--color-text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 45%; }
.xa-sum { font-size: 11px; color: var(--color-text-secondary); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.xa-dep { background: rgba(239,159,39,.15); color: #854F0B; padding: 1px 6px; border-radius: 3px; font-size: 9px; font-weight: 600; }
.xa-ep-body { padding: 11px 14px; border-top: 0.5px solid var(--color-border-tertiary); }
.xa-ep-body p { font-size: 11.5px; color: var(--color-text-secondary); line-height: 1.55; margin: 0 0 7px; }

.xa-no-spec { padding: 50px; text-align: center; color: var(--color-text-tertiary); font-size: 12px; background: var(--bg2, #FAFAFC); border-radius: 7px; display: flex; flex-direction: column; align-items: center; gap: 5px; }

/* Buttons */
.xa-btn { background: var(--color-background-primary); border: 0.5px solid var(--color-border-tertiary); padding: 6px 12px; border-radius: 6px; font-size: 11.5px; font-weight: 500; cursor: pointer; font-family: inherit; color: var(--color-text-secondary); display: inline-flex; align-items: center; gap: 4px; text-decoration: none; }
.xa-btn:hover:not(:disabled) { background: rgba(127,119,221,.05); }
.xa-btn:disabled { opacity: .55; cursor: not-allowed; }
.xa-btn-ghost { background: transparent; }
.xa-btn-primary { background: #7F77DD; color: #fff; border-color: #7F77DD; }
.xa-btn-primary:hover:not(:disabled) { background: var(--p-deep); }
.xa-btn-danger { background: rgba(226,75,74,.08); color: var(--sev-critical); border-color: rgba(226,75,74,.2); }
.xa-btn-danger:hover { background: var(--sev-high); color: #fff; }

/* Modal */
.xa-modal-bg { position: fixed; inset: 0; z-index: 1000; background: rgba(15,18,40,.45); -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; padding: 20px; }
.xa-modal { background: var(--color-background-primary); width: 100%; max-width: 480px; border-radius: 12px; overflow: hidden; box-shadow: 0 24px 64px rgba(15,23,60,.18); animation: xaIn .35s var(--ease-standard); }
@keyframes xaIn { from { transform: scale(.95) translateY(15px); opacity: 0; } to { transform: scale(1) translateY(0); opacity: 1; } }
.xa-modal-hd { padding: 12px 18px; background: linear-gradient(90deg, rgba(127,119,221,.06), transparent); border-bottom: 0.5px solid var(--color-border-tertiary); font-size: 12px; color: var(--color-text-primary); font-weight: 500; }
.xa-modal-body { padding: 14px 18px; display: flex; flex-direction: column; gap: 10px; max-height: 70dvh; overflow-y: auto; }
.xa-modal-footer { padding: 11px 18px; background: var(--bg2, #FAFAFC); border-top: 0.5px solid var(--color-border-tertiary); display: flex; gap: 6px; justify-content: flex-end; }
.xa-mgrid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.xa-field { display: flex; flex-direction: column; gap: 3px; }
.xa-field label { font-size: 9.5px; color: var(--color-text-tertiary); text-transform: uppercase; letter-spacing: .05em; }
.xa-field input, .xa-field textarea, .xa-field select { padding: 6px 10px; border: 0.5px solid var(--color-border-tertiary); border-radius: 6px; font-size: 12px; font-family: inherit; outline: none; }
.xa-field textarea { resize: vertical; }
</style>