<script setup lang="ts">
/**
 * Company Library · Detail page (Phase 3).
 *
 * Layout (mockup-approved):
 *   • Header full-width: avatar + breadcrumb + name + sublines + sync pill
 *   • Tab bar (system + custom) + "+ Раздел" button
 *   • 2-column grid:
 *       LEFT: Идентификация · Учредители · Отраслевые поля
 *       RIGHT: Финансы · Sync info · KPI · Рейтинги · Активность
 *   • Footer legend with 4 sync-source dots
 *
 * Field writes go via InlineCell → store.updateField → WebSocket broadcast.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter, RouterLink } from "vue-router";
import {
  companyLibraryApi,
  type LibraryCompanyDetail,
  type LibraryTab,
  type LibraryActivityEntry,
} from "@/api/companyLibrary";
import { useCompanyLibraryStore } from "@/stores/companyLibrary";
import InlineCell from "@/components/library/InlineCell.vue";
import SyncIndicator from "@/components/library/SyncIndicator.vue";
import ActivityFeed from "@/components/library/ActivityFeed.vue";
import CustomTabBuilder from "@/components/library/CustomTabBuilder.vue";
import ApiPanel from "@/components/library/ApiPanel.vue";
import CompanyApiTab from "@/components/library/CompanyApiTab.vue";
import TryItOutModal from "@/components/library/TryItOutModal.vue";
import type { CatalogEndpointWithSubstitution } from "@/api/apiCatalog";
import { useFormatters } from "@/composables/useFormatters";

const fmt = useFormatters();

const route   = useRoute();
const router  = useRouter();
const store   = useCompanyLibraryStore();

const companyId = computed(() => String(route.params.id || ""));

const detail   = ref<LibraryCompanyDetail | null>(null);
const loading  = ref(true);
const error    = ref<string | null>(null);
const activeTabCode = ref<string>("overview");
const activity = ref<LibraryActivityEntry[]>([]);
const tabBuilderOpen = ref(false);

async function loadDetail() {
  if (!companyId.value) return;
  loading.value = true;
  error.value = null;
  try {
    detail.value = await companyLibraryApi.detail(companyId.value);
    // Pick first available tab if current selection is gone
    if (detail.value.tabs.length > 0 && !detail.value.tabs.some(t => t.code === activeTabCode.value)) {
      activeTabCode.value = detail.value.tabs[0].code;
    }
  } catch (e: any) {
    if (e?.response?.status === 404) {
      error.value = "Компания не найдена";
    } else {
      error.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить карточку";
    }
  } finally {
    loading.value = false;
  }
}

async function loadActivity() {
  if (!companyId.value) return;
  try {
    activity.value = await companyLibraryApi.activity(companyId.value, 10);
  } catch {
    activity.value = [];
  }
}

onMounted(async () => {
  await loadDetail();
  await loadActivity();
  store.connectWebSocket();
});

watch(companyId, async () => {
  if (companyId.value) {
    await loadDetail();
    await loadActivity();
  }
});

onBeforeUnmount(() => store.disconnect());

// ── Lookups ────────────────────────────────────────────────────────
const fieldByCode = computed(() => {
  const m = new Map<string, any>();
  for (const f of detail.value?.fields || []) m.set(f.code, f);
  return m;
});

function defForCode(code: string) {
  return store.allFields.find(f => f.code === code) || null;
}

function valueForCode(code: string): any {
  const f = fieldByCode.value.get(code);
  return f ? f.value : null;
}

function sourceForCode(code: string): string | null {
  const f = fieldByCode.value.get(code);
  return f ? f.source_module : null;
}

// ── Tab sections ────────────────────────────────────────────────────
const activeTab = computed<LibraryTab | null>(() => {
  return detail.value?.tabs.find(t => t.code === activeTabCode.value) || null;
});

const identityCodes = ["name_ru", "name_short", "inn", "sector", "region", "employees", "founded_year"];
const founderCodes  = ["ceo_name"]; // future expansion
const financeCodes  = ["revenue", "ebitda", "net_profit", "total_assets"];
const ratingCodes   = ["rating_fitch", "rating_sp", "rating_moodys", "rating_esg"];
const kpiCodes      = ["kpi_completion"];

// Sector-scoped codes — pulled from fields that have source_module=null and scope_type=sector
const sectorScopedCodes = computed(() => {
  return (store.allFields || [])
    .filter(f => f.scope_type === "sector")
    .filter(f => fieldByCode.value.has(f.code))
    .map(f => f.code);
});

// Tab-specific field codes for custom tabs
const customTabFieldCodes = computed(() => {
  if (!activeTab.value) return [];
  return activeTab.value.field_codes;
});

const showCustomTabContent = computed(() =>
  activeTab.value && !["overview", "financials", "kpi", "ratings"].includes(activeTab.value.code),
);

// ── Format / actions (delegated to useFormatters) ─────────────────────
// `fmtMoney` and `fmtMonthsAgo` are kept as local thin wrappers so the
// existing template doesn't need surgical changes. They forward to the
// reactive composable so locale-switch updates everything in real-time.
function fmtMoney(v: number | null | undefined): string {
  return fmt.fmtMoneyCompact(v, "UZS");
}

function fmtMonthsAgo(iso: string | null | undefined): string {
  if (!iso) return "";
  return fmt.fmtRelativeTime(iso);
}

const companyAvatar = computed(() => {
  const code = detail.value?.company_code || "";
  return (code || detail.value?.company_name || "—").substring(0, 4).toUpperCase();
});

const sectorTone = computed(() => {
  // Simple hash → hue mapping for avatar background
  const code = detail.value?.company_code || detail.value?.company_name || "";
  let h = 0;
  for (const c of code) h = (h * 31 + c.charCodeAt(0)) & 0xff;
  const palette = ["#7F77DD", "#534AB7", "#378ADD", "#1D9E75", "#EF9F27", "#E24B4A"];
  return palette[h % palette.length];
});

// Open full Workspace page (for users who need the edit-heavy tools)
function openWorkspace() {
  if (detail.value?.company_code) {
    router.push(`/companies/${detail.value.company_code}/workspace`);
  }
}

async function onTabCreated() {
  tabBuilderOpen.value = false;
  await loadDetail();
}

// Phase 5.3 · ApiPanel show/hide pref (saved in localStorage)
const LS_API_PANEL = "uza-library-api-panel-open";
const apiPanelOpen = ref(localStorage.getItem(LS_API_PANEL) !== "0");
function toggleApiPanel() {
  apiPanelOpen.value = !apiPanelOpen.value;
  localStorage.setItem(LS_API_PANEL, apiPanelOpen.value ? "1" : "0");
}

const isApiTab = computed(() => activeTabCode.value === "api");

// Phase 5.6 · TryItOut modal state
const tryOpen = ref(false);
const tryEndpoint = ref<CatalogEndpointWithSubstitution | null>(null);
function openTry(ep: CatalogEndpointWithSubstitution) {
  tryEndpoint.value = ep;
  tryOpen.value = true;
}

const allTabs = computed(() => {
  // Synthesize a built-in "api" tab even if it's not in DB
  const tabs = [...(detail.value?.tabs || [])];
  if (!tabs.some(t => t.code === "api")) {
    tabs.push({
      id: "__api__", code: "api", name_ru: "API · Интеграция",
      name_uz: null, name_en: null,
      field_codes: [], layout: "one_col" as const, is_system: true,
      sort_order: 9999, scope_type: "all" as const, scope_value: null,
      created_by: null,
      created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
    });
  }
  return tabs;
});
</script>

<template>
  <div class="cld-page">
    <!-- ═══ LOADING / ERROR ═══ -->
    <div v-if="loading" class="cld-loading">Загружаю карточку компании…</div>
    <div v-else-if="error" class="cld-error">
      <div>{{ error }}</div>
      <RouterLink to="/library/companies" class="cld-back-link">← К списку компаний</RouterLink>
    </div>

    <template v-else-if="detail">
      <!-- ═══ HEADER ═══ -->
      <header class="cld-head">
        <div class="cld-head-l">
          <div class="cld-avatar" :style="{ background: sectorTone + '22', color: sectorTone, borderColor: sectorTone + '55' }">
            {{ companyAvatar }}
          </div>
          <div class="cld-head-text">
            <RouterLink to="/library/companies" class="cld-breadcrumb">← Библиотека</RouterLink>
            <h1 class="cld-title">{{ detail.company_name }}</h1>
            <div class="cld-subline">
              <span v-if="valueForCode('inn')">ИНН {{ valueForCode("inn") }}</span>
              <span v-if="detail.sector_name">· {{ detail.sector_name }}</span>
              <span v-if="valueForCode('region')">· {{ valueForCode("region") }}</span>
              <span v-if="valueForCode('employees')">· {{ valueForCode("employees") }} сотр.</span>
            </div>
          </div>
        </div>
        <div class="cld-head-r">
          <span class="cld-live" :title="store.wsConnected ? 'Real-time sync включена' : 'Offline'">
            <span class="cld-live-dot" :class="{ 'cld-live-dot-on': store.wsConnected }"></span>
            {{ store.wsConnected ? "Live" : "Offline" }}
          </span>
          <button
            class="cld-btn cld-btn-secondary"
            :class="{ 'cld-btn-active': apiPanelOpen }"
            @click="toggleApiPanel"
            title="Панель API endpoints"
            v-if="!isApiTab"
          >{{ apiPanelOpen ? "API ✓" : "API" }}</button>
          <button class="cld-btn cld-btn-secondary" @click="openWorkspace" :disabled="!detail.company_code">
            Открыть Workspace →
          </button>
        </div>
      </header>

      <!-- ═══ TAB BAR ═══ -->
      <nav class="cld-tabs">
        <button
          v-for="t in allTabs"
          :key="t.code"
          class="cld-tab"
          :class="{ active: activeTabCode === t.code, 'cld-tab-api': t.code === 'api' }"
          @click="activeTabCode = t.code"
        >
          {{ t.name_ru }}
          <span v-if="t.field_codes.length" class="cld-tab-count">{{ t.field_codes.length }}</span>
        </button>
        <button class="cld-tab cld-tab-add" @click="tabBuilderOpen = true">+ Раздел</button>
      </nav>

      <!-- ═══ TAB CONTENT ═══ -->
      <!-- API · Интеграция — full-width tab, replaces 2-col layout -->
      <main v-if="isApiTab" class="cld-api-wrap">
        <CompanyApiTab :company-id="companyId" @open-try="openTry" />
      </main>

      <main v-else class="cld-content-row" :class="{ 'cld-with-api': apiPanelOpen }">
        <div class="cld-grid">

        <!-- ════════ TAB: Обзор ════════ -->
        <template v-if="activeTabCode === 'overview'">
          <!-- ===== LEFT ===== -->
          <section class="cld-col cld-col-l">
            <article class="cld-card">
              <header class="cld-card-h">Идентификация</header>
              <div class="cld-kv-list">
                <template v-for="code in identityCodes" :key="code">
                  <div v-if="defForCode(code) && fieldByCode.has(code)" class="cld-kv-row">
                    <span class="cld-kv-k">{{ defForCode(code)!.name_ru }}</span>
                    <span class="cld-kv-v">
                      <InlineCell :company-id="companyId" :field-code="code"
                                  :field-def="defForCode(code)!" :value="valueForCode(code)" />
                    </span>
                  </div>
                </template>
              </div>
            </article>

            <article v-if="sectorScopedCodes.length" class="cld-card cld-card-sector">
              <header class="cld-card-h">
                Отраслевые поля
                <span v-if="detail.sector_name" class="cld-card-h-sub">· {{ detail.sector_name }}</span>
              </header>
              <div class="cld-kv-list">
                <div v-for="code in sectorScopedCodes" :key="code" class="cld-kv-row">
                  <span class="cld-kv-k">
                    {{ defForCode(code)?.name_ru }}
                    <span v-if="defForCode(code)?.unit" class="cld-kv-unit">· {{ defForCode(code)?.unit }}</span>
                  </span>
                  <span class="cld-kv-v">
                    <InlineCell :company-id="companyId" :field-code="code"
                                :field-def="defForCode(code)!" :value="valueForCode(code)" />
                  </span>
                </div>
              </div>
            </article>
          </section>

          <!-- ===== RIGHT ===== -->
          <section class="cld-col cld-col-r">
            <article class="cld-card">
              <header class="cld-card-h">
                Финансы <span class="cld-card-h-sub">· последние факты</span>
              </header>
              <div class="cld-fin-grid">
                <template v-for="code in financeCodes" :key="code">
                  <div v-if="defForCode(code)" class="cld-fin-cell">
                    <div class="cld-fin-cell-h">
                      {{ defForCode(code)?.name_ru }}
                      <SyncIndicator :source-module="sourceForCode(code)" :size="6" />
                    </div>
                    <div class="cld-fin-cell-v">{{ fmtMoney(valueForCode(code) as number) }}</div>
                    <div v-if="defForCode(code)?.unit" class="cld-fin-cell-u">{{ defForCode(code)?.unit }}</div>
                  </div>
                </template>
              </div>
              <div class="cld-fin-sync">
                <SyncIndicator source-module="finmodel" :size="6" />
                <span>Sync с FinModel</span>
                <button class="cld-fin-sync-link" @click="activeTabCode = 'financials'">Все показатели →</button>
              </div>
            </article>

            <article v-if="defForCode('kpi_completion')" class="cld-card">
              <header class="cld-card-h">KPI <span class="cld-card-h-sub">· общее выполнение</span></header>
              <div class="cld-kpi-block">
                <div class="cld-kpi-num">
                  {{ valueForCode("kpi_completion") != null ? fmt.fmtPercent(Number(valueForCode("kpi_completion")), { decimals: 0 }) : "—" }}
                </div>
                <div class="cld-kpi-bar-track">
                  <div v-if="valueForCode('kpi_completion') != null" class="cld-kpi-bar"
                       :style="{
                         width: Math.min(100, Number(valueForCode('kpi_completion')) || 0) + '%',
                         background: (Number(valueForCode('kpi_completion')) || 0) >= 70 ? '#1D9E75'
                                   : (Number(valueForCode('kpi_completion')) || 0) >= 35 ? '#EF9F27' : '#E24B4A',
                       }"></div>
                </div>
                <div class="cld-kpi-foot">
                  <SyncIndicator source-module="kpi" :size="6" />
                  <span>Источник: KPI editor</span>
                </div>
              </div>
            </article>

            <article class="cld-card">
              <header class="cld-card-h">Рейтинги <span class="cld-card-h-sub">· последние оценки</span></header>
              <div class="cld-rat-grid">
                <template v-for="code in ratingCodes" :key="code">
                  <div v-if="defForCode(code)" class="cld-rat-cell">
                    <div class="cld-rat-cell-h">{{ defForCode(code)?.name_ru }}</div>
                    <div class="cld-rat-cell-v">{{ valueForCode(code) || "—" }}</div>
                    <SyncIndicator source-module="ratings" :size="5" class="cld-rat-cell-dot" />
                  </div>
                </template>
              </div>
            </article>

            <ActivityFeed :entries="activity" />
          </section>
        </template>

        <!-- ════════ TAB: Финансы ════════ -->
        <template v-else-if="activeTabCode === 'financials'">
          <section class="cld-col cld-col-l cld-col-wide">
            <article class="cld-card">
              <header class="cld-card-h">
                Финансовые показатели
                <span class="cld-card-h-sub">· {{ detail.company_name }}</span>
              </header>
              <div class="cld-fin-grid-lg">
                <template v-for="code in financeCodes" :key="code">
                  <div v-if="defForCode(code)" class="cld-fin-cell cld-fin-cell-lg">
                    <div class="cld-fin-cell-h">
                      {{ defForCode(code)?.name_ru }}
                      <SyncIndicator :source-module="sourceForCode(code)" :size="6" />
                    </div>
                    <div class="cld-fin-cell-v cld-fin-cell-v-lg">
                      {{ fmtMoney(valueForCode(code) as number) }}
                    </div>
                    <div v-if="defForCode(code)?.unit" class="cld-fin-cell-u">{{ defForCode(code)?.unit }}</div>
                  </div>
                </template>
              </div>
              <div class="cld-fin-sync">
                <SyncIndicator source-module="finmodel" :size="6" />
                <span>Sync с FinModel · обновление в real-time</span>
                <RouterLink
                  v-if="detail.company_code"
                  :to="`/companies/${detail.company_code}/workspace`"
                  class="cld-fin-sync-link"
                >Открыть в FinModel ↗</RouterLink>
              </div>
            </article>

            <article class="cld-card">
              <header class="cld-card-h">Все финансовые поля</header>
              <div class="cld-kv-list">
                <template v-for="code in financeCodes" :key="code">
                  <div v-if="defForCode(code) && fieldByCode.has(code)" class="cld-kv-row">
                    <span class="cld-kv-k">
                      {{ defForCode(code)?.name_ru }}
                      <span v-if="defForCode(code)?.unit" class="cld-kv-unit">· {{ defForCode(code)?.unit }}</span>
                      <SyncIndicator :source-module="sourceForCode(code)" :size="5" />
                    </span>
                    <span class="cld-kv-v">
                      <InlineCell :company-id="companyId" :field-code="code"
                                  :field-def="defForCode(code)!" :value="valueForCode(code)" />
                    </span>
                  </div>
                </template>
                <div v-if="defForCode('debt_to_ebitda')" class="cld-kv-row">
                  <span class="cld-kv-k">Долг / EBITDA</span>
                  <span class="cld-kv-v">
                    {{ valueForCode("debt_to_ebitda") != null
                       ? fmt.fmtNumber(Number(valueForCode("debt_to_ebitda")), { decimals: 2 }) + "x"
                       : "—" }}
                  </span>
                </div>
              </div>
            </article>
          </section>
        </template>

        <!-- ════════ TAB: KPI · BP ════════ -->
        <template v-else-if="activeTabCode === 'kpi'">
          <section class="cld-col cld-col-l cld-col-wide">
            <article class="cld-card">
              <header class="cld-card-h">
                KPI <span class="cld-card-h-sub">· общее выполнение по компании</span>
              </header>
              <div class="cld-kpi-block cld-kpi-block-lg">
                <div class="cld-kpi-num cld-kpi-num-lg">
                  {{ valueForCode("kpi_completion") != null ? fmt.fmtPercent(Number(valueForCode("kpi_completion")), { decimals: 0 }) : "—" }}
                </div>
                <div class="cld-kpi-bar-track">
                  <div v-if="valueForCode('kpi_completion') != null" class="cld-kpi-bar"
                       :style="{
                         width: Math.min(100, Number(valueForCode('kpi_completion')) || 0) + '%',
                         background: (Number(valueForCode('kpi_completion')) || 0) >= 70 ? '#1D9E75'
                                   : (Number(valueForCode('kpi_completion')) || 0) >= 35 ? '#EF9F27' : '#E24B4A',
                       }"></div>
                </div>
                <div class="cld-kpi-foot">
                  <SyncIndicator source-module="kpi" :size="6" />
                  <span>Источник: KPI editor · автоматически</span>
                  <RouterLink
                    v-if="detail.company_code"
                    :to="`/companies/${detail.company_code}/workspace`"
                    class="cld-fin-sync-link"
                  >Открыть KPI editor ↗</RouterLink>
                </div>
              </div>
            </article>

            <article class="cld-card">
              <header class="cld-card-h">Подробности</header>
              <p class="cld-tab-hint">
                Детальная разбивка по руководителям, индикаторам, весам и квартальной декомпозиции — в
                <RouterLink v-if="detail.company_code"
                            :to="`/companies/${detail.company_code}/workspace`"
                            class="cld-tab-link">Workspace · KPI</RouterLink>.
                Здесь — только агрегированный показатель выполнения, синхронизированный из KPI-модуля.
              </p>
            </article>
          </section>
        </template>

        <!-- ════════ TAB: Рейтинги ════════ -->
        <template v-else-if="activeTabCode === 'ratings'">
          <section class="cld-col cld-col-l cld-col-wide">
            <article class="cld-card">
              <header class="cld-card-h">
                Рейтинги агентств
                <span class="cld-card-h-sub">· последние оценки + дата</span>
              </header>
              <div class="cld-rat-grid cld-rat-grid-lg">
                <template v-for="code in ratingCodes" :key="code">
                  <div v-if="defForCode(code)" class="cld-rat-cell cld-rat-cell-lg">
                    <div class="cld-rat-cell-h">{{ defForCode(code)?.name_ru }}</div>
                    <div class="cld-rat-cell-v cld-rat-cell-v-lg">{{ valueForCode(code) || "—" }}</div>
                    <SyncIndicator source-module="ratings" :size="5" class="cld-rat-cell-dot" />
                  </div>
                </template>
              </div>
              <div class="cld-fin-sync">
                <SyncIndicator source-module="ratings" :size="6" />
                <span>Sync с модулем Рейтинги · upsert через двойной клик</span>
              </div>
            </article>

            <article class="cld-card">
              <header class="cld-card-h">Все рейтинговые поля</header>
              <div class="cld-kv-list">
                <template v-for="code in ratingCodes" :key="code">
                  <div v-if="defForCode(code) && fieldByCode.has(code)" class="cld-kv-row">
                    <span class="cld-kv-k">
                      {{ defForCode(code)?.name_ru }}
                      <SyncIndicator source-module="ratings" :size="5" />
                    </span>
                    <span class="cld-kv-v">
                      <InlineCell :company-id="companyId" :field-code="code"
                                  :field-def="defForCode(code)!" :value="valueForCode(code)" />
                    </span>
                  </div>
                </template>
              </div>
            </article>
          </section>
        </template>

        <!-- ════════ Custom tab (user-created) ════════ -->
        <template v-else-if="activeTab">
          <section class="cld-col cld-col-l cld-col-wide">
            <article class="cld-card">
              <header class="cld-card-h">{{ activeTab.name_ru }}</header>
              <div v-if="customTabFieldCodes.length" class="cld-kv-list">
                <template v-for="code in customTabFieldCodes" :key="code">
                  <div v-if="defForCode(code) && fieldByCode.has(code)" class="cld-kv-row">
                    <span class="cld-kv-k">
                      {{ defForCode(code)?.name_ru }}
                      <span v-if="defForCode(code)?.unit" class="cld-kv-unit">· {{ defForCode(code)?.unit }}</span>
                    </span>
                    <span class="cld-kv-v">
                      <InlineCell :company-id="companyId" :field-code="code"
                                  :field-def="defForCode(code)!" :value="valueForCode(code)" />
                    </span>
                  </div>
                </template>
              </div>
              <p v-else class="cld-tab-hint">В этот раздел не добавлены поля. Откройте «+ Раздел» чтобы создать новый, или включите поля в Column Manager.</p>
            </article>
          </section>
        </template>

        </div>

        <!-- ApiPanel docked right when toggled on -->
        <ApiPanel
          v-if="apiPanelOpen"
          :company-id="companyId"
          :current-tab="activeTabCode"
          @open-try="openTry"
        />
      </main>

      <!-- ═══ FOOTER LEGEND ═══ -->
      <footer class="cld-footer">
        <div class="cld-legend">
          <span class="cld-legend-item">
            <SyncIndicator source-module="finmodel" :size="7" /> Sync с FinModel
          </span>
          <span class="cld-legend-item">
            <SyncIndicator source-module="kpi" :size="7" /> KPI
          </span>
          <span class="cld-legend-item">
            <SyncIndicator source-module="ratings" :size="7" /> Рейтинги
          </span>
          <span class="cld-legend-item">
            <SyncIndicator :source-module="null" :size="7" /> Custom (только в библиотеке)
          </span>
        </div>
        <div class="cld-legend-hint">
          Любое поле редактируется здесь — обновление транслируется во все модули в real-time
        </div>
      </footer>
    </template>

    <CustomTabBuilder
      :open="tabBuilderOpen"
      @close="tabBuilderOpen = false"
      @created="onTabCreated"
    />

    <TryItOutModal
      :open="tryOpen"
      :endpoint="tryEndpoint"
      @close="tryOpen = false"
    />
  </div>
</template>

<style scoped>
.cld-page {
  display: flex; flex-direction: column;
  min-height: 100vh;
  background: var(--bg2, #FAFAFC);
}

.cld-loading,
.cld-error { padding: 60px 28px; text-align: center; color: var(--t3, var(--t-muted)); font-size: 13px; }
.cld-back-link { display: inline-block; margin-top: 12px; color: var(--p-deep); text-decoration: none; }
.cld-back-link:hover { text-decoration: underline; }

/* ── Header ── */
.cld-head {
  display: flex; justify-content: space-between; align-items: flex-start;
  padding: 18px 28px 14px;
  border-bottom: 0.5px solid #F1EFE8;
}
.cld-head-l { display: flex; gap: 14px; align-items: center; flex: 1; min-width: 0; }
.cld-avatar {
  width: 52px; height: 52px;
  border-radius: 11px;
  border: 1px solid;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 500; letter-spacing: 0.02em;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}
.cld-head-text { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.cld-breadcrumb { font-size: 11px; color: var(--t3, var(--t-muted)); text-decoration: none; transition: color 120ms; }
.cld-breadcrumb:hover { color: var(--p-deep); }
.cld-title { font-size: 18px; font-weight: 500; letter-spacing: -0.01em; color: var(--t1, #1E2A4A); margin: 2px 0 0 0; }
.cld-subline { font-size: 11.5px; color: var(--t3, var(--t-muted)); display: flex; flex-wrap: wrap; gap: 5px; margin-top: 2px; }

.cld-head-r { display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
.cld-live { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--t3, var(--t-muted)); }
.cld-live-dot { width: 7px; height: 7px; border-radius: 50%; background: #C8C7C0; }
.cld-live-dot-on { background: var(--green); box-shadow: 0 0 0 0 rgba(29,158,117,0.6); animation: cldLivePulse 2s ease-out infinite; }
@keyframes cldLivePulse { 0%, 100% { box-shadow: 0 0 0 0 rgba(29,158,117,0.6); } 50% { box-shadow: 0 0 0 4px rgba(29,158,117,0); } }

/* ── Tab bar ── */
.cld-tabs {
  display: flex; gap: 4px; padding: 8px 28px 0;
  border-bottom: 0.5px solid #F1EFE8;
  overflow-x: auto;
}
.cld-tab {
  background: transparent; border: none; cursor: pointer;
  padding: 8px 14px; border-radius: 8px 8px 0 0;
  font-size: 12px; font-weight: 500; color: var(--t3, var(--t-muted));
  display: flex; align-items: center; gap: 6px;
  position: relative;
  transition: color 120ms, background 120ms;
}
.cld-tab:hover { color: var(--t1, #1E2A4A); background: rgba(127,119,221,.06); }
.cld-tab.active { color: var(--t1, #1E2A4A); background: white; }
.cld-tab.active::after { content: ""; position: absolute; left: 0; right: 0; bottom: -1px; height: 2px; background: #7F77DD; }
.cld-tab-count { font-size: 9.5px; color: #C8C7C0; background: rgba(127,119,221,.07); padding: 1px 5px; border-radius: 8px; }
.cld-tab-add { color: var(--p-deep); border: 1px dashed rgba(127,119,221,.4); margin-left: 8px; }

/* ── 2-col grid ── */
.cld-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  padding: 16px 28px;
  flex: 1;
}
.cld-col { display: flex; flex-direction: column; gap: 14px; min-width: 0; }

.cld-card {
  background: white;
  border-radius: 12px;
  padding: 14px 16px;
  border: 0.5px solid #F1EFE8;
  display: flex; flex-direction: column; gap: 10px;
}
.cld-card-sector { background: rgba(127,119,221,.04); border-color: rgba(127,119,221,.18); }
.cld-card-h {
  font-size: 10.5px; font-weight: 500; letter-spacing: 0.06em; text-transform: uppercase;
  color: var(--t3, var(--t-muted));
  display: flex; align-items: baseline; gap: 6px;
}
.cld-card-h-sub { text-transform: none; letter-spacing: 0; font-size: 10px; color: #C8C7C0; font-weight: 400; }

/* ── Key-value list ── */
.cld-kv-list { display: flex; flex-direction: column; gap: 4px; }
.cld-kv-row {
  display: grid; grid-template-columns: 130px 1fr; gap: 10px;
  align-items: center;
  padding: 4px 0;
  border-bottom: 0.5px dashed rgba(15,23,60,.04);
}
.cld-kv-row:last-child { border-bottom: none; }
.cld-kv-k { font-size: 11.5px; color: var(--t3, var(--t-muted)); font-weight: 500; }
.cld-kv-unit { color: #C8C7C0; font-size: 10px; font-weight: 400; }
.cld-kv-v { font-size: 13px; color: var(--t1, #1E2A4A); font-variant-numeric: tabular-nums; }

/* ── Finance mini-cards ── */
.cld-fin-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 8px;
}
.cld-fin-cell {
  background: rgba(127,119,221,.04);
  border-radius: 8px;
  padding: 10px 12px;
  display: flex; flex-direction: column; gap: 2px;
}
.cld-fin-cell-h { font-size: 10px; letter-spacing: 0.04em; text-transform: uppercase; color: var(--t3, var(--t-muted)); font-weight: 500; display: flex; align-items: center; gap: 6px; }
.cld-fin-cell-v { font-size: 17px; font-weight: 500; color: var(--t1, #1E2A4A); font-variant-numeric: tabular-nums; letter-spacing: -0.01em; line-height: 1.1; }
.cld-fin-cell-u { font-size: 10px; color: var(--t3, var(--t-muted)); }

.cld-fin-sync {
  display: flex; align-items: center; gap: 8px;
  font-size: 11px; color: var(--t3, var(--t-muted));
  margin-top: 6px;
  padding-top: 8px;
  border-top: 0.5px dashed rgba(15,23,60,.06);
}
.cld-fin-sync-link { margin-left: auto; color: var(--p-deep); text-decoration: none; }
.cld-fin-sync-link:hover { text-decoration: underline; }

/* ── KPI block ── */
.cld-kpi-block { display: flex; flex-direction: column; gap: 8px; }
.cld-kpi-num { font-size: 26px; font-weight: 500; color: var(--t1, #1E2A4A); letter-spacing: -0.02em; font-variant-numeric: tabular-nums; line-height: 1; }
.cld-kpi-bar-track { height: 8px; background: rgba(15,23,60,.06); border-radius: 4px; overflow: hidden; }
.cld-kpi-bar { height: 100%; border-radius: 4px; transition: width 600ms var(--ease-standard); }
.cld-kpi-foot { display: flex; align-items: center; gap: 8px; font-size: 11px; color: var(--t3, var(--t-muted)); }

/* ── Ratings mini-cards ── */
.cld-rat-grid {
  display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px;
}
.cld-rat-cell {
  background: rgba(127,119,221,.04);
  border-radius: 8px;
  padding: 10px 12px;
  display: flex; flex-direction: column; gap: 3px;
  position: relative;
}
.cld-rat-cell-h { font-size: 10px; letter-spacing: 0.04em; text-transform: uppercase; color: var(--t3, var(--t-muted)); font-weight: 500; }
.cld-rat-cell-v { font-size: 18px; font-weight: 500; color: var(--t1, #1E2A4A); font-variant-numeric: tabular-nums; letter-spacing: -0.01em; }
.cld-rat-cell-dot { position: absolute; top: 8px; right: 8px; }

/* ── Footer ── */
.cld-footer {
  padding: 12px 28px;
  border-top: 0.5px solid #F1EFE8;
  display: flex; justify-content: space-between; align-items: center; gap: 16px;
  font-size: 11px;
}
.cld-legend { display: flex; gap: 16px; flex-wrap: wrap; }
.cld-legend-item { display: flex; align-items: center; gap: 6px; color: var(--t1, #1E2A4A); }
.cld-legend-hint { color: var(--t3, var(--t-muted)); font-style: italic; }

/* ── Buttons ── */
.cld-btn { padding: 7px 14px; border-radius: 8px; font-size: 12px; font-weight: 500; cursor: pointer; border: 1px solid transparent; transition: all 150ms; }
.cld-btn-secondary { background: white; color: var(--t1, #1E2A4A); border-color: var(--border-hard); }
.cld-btn-secondary:hover:not(:disabled) { background: rgba(15,23,60,.04); }
.cld-btn-secondary:disabled { opacity: .55; cursor: not-allowed; }
.cld-btn-active { background: rgba(127,119,221,.10); border-color: rgba(127,119,221,.4); color: var(--p-deep); }

/* ── Phase 5.3-5.4: API panel docked right + API tab full width ── */
.cld-content-row { display: flex; flex: 1; min-height: 0; }
.cld-content-row .cld-grid { flex: 1; }

.cld-api-wrap {
  flex: 1;
  padding: 16px 28px;
  overflow-y: auto;
}

.cld-tab-api {
  color: var(--p-deep);
  font-style: normal;
}
.cld-tab-api.active { color: var(--p-deep); }

/* Wide single-col when tab is focused on one area */
.cld-col-wide { grid-column: 1 / -1; }

/* Large finance cells for /financials tab */
.cld-fin-grid-lg {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}
.cld-fin-cell-lg { padding: 14px 16px; }
.cld-fin-cell-v-lg { font-size: 22px; letter-spacing: -0.015em; }

/* Big KPI block for /kpi tab */
.cld-kpi-block-lg { padding: 10px 0; }
.cld-kpi-num-lg   { font-size: 48px; line-height: 1; }

/* Large rating cells for /ratings tab */
.cld-rat-grid-lg {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
}
.cld-rat-cell-lg { padding: 14px 16px; }
.cld-rat-cell-v-lg { font-size: 24px; letter-spacing: -0.02em; }

/* Sync-link button styling (no underline, hover state) */
.cld-fin-sync-link {
  background: transparent; border: none; cursor: pointer;
  margin-left: auto;
  color: var(--p-deep);
  font-size: 11.5px;
  padding: 0;
  text-decoration: none;
  font: inherit;
}
.cld-fin-sync-link:hover { text-decoration: underline; }

/* Generic tab hint paragraph */
.cld-tab-hint {
  font-size: 12.5px;
  color: var(--t3, var(--t-muted));
  line-height: 1.55;
  margin: 0;
}
.cld-tab-link {
  color: var(--p-deep);
  text-decoration: none;
}
.cld-tab-link:hover { text-decoration: underline; }

@media (max-width: 900px) {
  .cld-grid { grid-template-columns: 1fr; }
  .cld-content-row { flex-direction: column; }
}
</style>
