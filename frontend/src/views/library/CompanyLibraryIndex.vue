<script setup lang="ts">
/**
 * Company Library · Index page (Phase 2).
 *
 * Layout (top → bottom):
 *   1) Header — title + buttons (Колонки · N / Экспорт / + Добавить)
 *   2) Filter row — search input + sector dropdown + live-sync indicator
 *   3) Sticky-header table with InlineCell editable cells
 *   4) Footer — counter + pagination placeholder
 */
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useCompanyLibraryStore } from "@/stores/companyLibrary";
import { companiesApi } from "@/api/companies";
import InlineCell from "@/components/library/InlineCell.vue";
import ColumnManagerModal from "@/components/library/ColumnManagerModal.vue";
import CustomFieldBuilder from "@/components/library/CustomFieldBuilder.vue";

const store  = useCompanyLibraryStore();
const router = useRouter();

const sectors = ref<{ code: string; name_ru: string }[]>([]);
const columnsModalOpen = ref(false);
const fieldBuilderOpen = ref(false);

onMounted(async () => {
  // Fetch sectors for the filter dropdown
  try {
    const list = await companiesApi.listSectors();
    sectors.value = list.map((s: any) => ({
      code: s.code,
      name_ru: s.name_ru || s.name || s.code,
    }));
  } catch { /* non-fatal */ }
  await Promise.all([store.load(), store.loadAllFields(), store.loadTabs()]);
  store.connectWebSocket();
});

onBeforeUnmount(() => store.disconnect());

function rowToDetail(co: { id: string; code: string | null }) {
  router.push(`/library/companies/${co.id}`);
}

// Filter handlers — debounced search
let searchTimer: ReturnType<typeof setTimeout> | null = null;
function onSearchInput(v: string) {
  store.setSearch(v);
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(() => store.load(), 300);
}
function onSectorChange(code: string | null) {
  store.setSectorFilter(code);
  store.loadAllFields(code || undefined);
  store.load();
}
function onSort(code: string) {
  store.setSort(code);
}

const lastUpdatedHint = computed(() => {
  if (!store.lastLoadedAt) return "";
  const ago = Math.round((Date.now() - store.lastLoadedAt) / 1000);
  if (ago < 60) return `${ago} с назад`;
  return `${Math.round(ago / 60)} мин назад`;
});
</script>

<template>
  <div class="cl-page">
    <!-- ═══ HEADER ═══ -->
    <header class="cl-page-header">
      <div class="cl-page-title-block">
        <div class="cl-page-eyebrow">Библиотека · MDM</div>
        <h1 class="cl-page-title">Компании</h1>
      </div>
      <div class="cl-page-actions">
        <button class="cl-btn cl-btn-secondary" @click="columnsModalOpen = true">
          Колонки · {{ store.visibleColumns.length }}
        </button>
        <button class="cl-btn cl-btn-secondary" disabled title="Скоро">Экспорт</button>
        <button class="cl-btn cl-btn-primary" disabled title="Скоро">+ Добавить</button>
      </div>
    </header>

    <!-- ═══ FILTER ROW ═══ -->
    <div class="cl-filters">
      <input
        type="text"
        class="cl-search"
        placeholder="Поиск по названию, ИНН…"
        :value="store.searchQuery"
        @input="onSearchInput(($event.target as HTMLInputElement).value)"
      />
      <select
        class="cl-select"
        :value="store.sectorFilter || ''"
        @change="onSectorChange(($event.target as HTMLSelectElement).value || null)"
      >
        <option value="">Все сектора</option>
        <option v-for="s in sectors" :key="s.code" :value="s.code">{{ s.name_ru }}</option>
      </select>

      <div class="cl-live">
        <span
          class="cl-live-dot"
          :class="{ 'cl-live-dot-on': store.wsConnected }"
          :title="store.wsConnected ? 'Real-time sync включена' : 'Offline — данные обновятся вручную'"
        ></span>
        <span class="cl-live-label">{{ store.wsConnected ? "Live" : "Offline" }}</span>
        <span v-if="lastUpdatedHint" class="cl-live-sub">· обновлено {{ lastUpdatedHint }}</span>
      </div>

      <div class="cl-counter">{{ store.companies.length }} / {{ store.total || store.companies.length }}</div>
    </div>

    <!-- ═══ ERROR / LOADING ═══ -->
    <div v-if="store.error" class="cl-error">{{ store.error }}</div>
    <div v-else-if="store.loading && store.companies.length === 0" class="cl-loading">Загружаю компании…</div>

    <!-- ═══ TABLE ═══ -->
    <div v-else class="cl-table-wrap">
      <table class="cl-table">
        <thead>
          <tr>
            <th class="cl-th cl-th-name" @click="onSort('name_ru')">
              <span class="cl-th-label">Компания</span>
              <span v-if="store.sortBy === 'name_ru'" class="cl-th-sort">{{ store.sortDir === "asc" ? "↑" : "↓" }}</span>
            </th>
            <th
              v-for="col in store.visibleColumns"
              :key="col.code"
              class="cl-th"
              :class="{
                'cl-th-num':    col.field_type === 'number',
                'cl-th-sector': col.scope_type === 'sector',
              }"
              @click="onSort(col.code)"
            >
              <span class="cl-th-label" :title="col.name_ru">{{ col.name_ru }}</span>
              <span v-if="col.unit" class="cl-th-unit">{{ col.unit }}</span>
              <span v-if="store.sortBy === col.code" class="cl-th-sort">{{ store.sortDir === "asc" ? "↑" : "↓" }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="co in store.companies"
            :key="co.id"
            class="cl-tr"
            @click="rowToDetail(co)"
          >
            <td class="cl-td cl-td-name">
              <div class="cl-co-name">
                <span class="cl-co-short">{{ co.name_short || co.name_ru }}</span>
                <span v-if="co.sector_name" class="cl-co-sector">{{ co.sector_name }}</span>
              </div>
            </td>
            <td
              v-for="col in store.visibleColumns"
              :key="col.code"
              class="cl-td"
              :class="{ 'cl-td-num': col.field_type === 'number', 'cl-td-sector': col.scope_type === 'sector' }"
              @click.stop
            >
              <InlineCell
                :company-id="co.id"
                :field-code="col.code"
                :field-def="col"
                :value="co.fields[col.code]"
              />
            </td>
          </tr>
          <tr v-if="store.companies.length === 0">
            <td :colspan="1 + store.visibleColumns.length" class="cl-empty">
              Нет компаний по текущему фильтру.
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- ═══ MODALS ═══ -->
    <ColumnManagerModal
      :open="columnsModalOpen"
      @close="columnsModalOpen = false"
      @open-builder="() => { columnsModalOpen = false; fieldBuilderOpen = true; }"
    />
    <CustomFieldBuilder
      :open="fieldBuilderOpen"
      @close="fieldBuilderOpen = false"
      @created="() => { fieldBuilderOpen = false; }"
    />
  </div>
</template>

<style scoped>
.cl-page {
  display: flex; flex-direction: column;
  min-height: 100vh;
  background: var(--bg2, #FAFAFC);
}

/* ── Header ── */
.cl-page-header {
  display: flex; justify-content: space-between; align-items: flex-end;
  padding: 18px 28px 12px;
}
.cl-page-eyebrow { font-size: 10px; letter-spacing: 0.08em; color: var(--t3, var(--t-muted)); font-weight: 500; text-transform: uppercase; }
.cl-page-title   { font-size: 22px; font-weight: 500; color: var(--t1, #1E2A4A); letter-spacing: -0.015em; margin: 2px 0 0 0; }
.cl-page-actions { display: flex; gap: 8px; }

/* ── Filter row ── */
.cl-filters {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 28px 14px;
  border-bottom: 0.5px solid #F1EFE8;
}
.cl-search { flex: 1; max-width: 340px; padding: 7px 11px; border: 1px solid var(--border-hard); border-radius: 8px; font-size: 12.5px; outline: none; background: white; }
.cl-search:focus { border-color: #7F77DD; box-shadow: 0 0 0 2px rgba(127,119,221,.15); }
.cl-select { padding: 7px 11px; border: 1px solid var(--border-hard); border-radius: 8px; font-size: 12.5px; background: white; color: var(--t1, #1E2A4A); cursor: pointer; }

.cl-live { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--t3, var(--t-muted)); }
.cl-live-dot { width: 7px; height: 7px; border-radius: 50%; background: #C8C7C0; transition: background 180ms; }
.cl-live-dot-on { background: var(--green); box-shadow: 0 0 0 0 rgba(29,158,117,0.6); animation: clLivePulse 2s ease-out infinite; }
@keyframes clLivePulse { 0%, 100% { box-shadow: 0 0 0 0 rgba(29,158,117,0.6); } 50% { box-shadow: 0 0 0 4px rgba(29,158,117,0); } }
.cl-live-label { font-weight: 500; color: var(--t1, #1E2A4A); }
.cl-live-sub   { color: var(--t3, var(--t-muted)); }

.cl-counter { margin-left: auto; font-size: 11.5px; color: var(--t3, var(--t-muted)); font-variant-numeric: tabular-nums; }

/* ── Error / loading ── */
.cl-error    { margin: 18px 28px; padding: 12px 16px; background: rgba(226,75,74,.08); color: #A82C2B; border-radius: 8px; font-size: 13px; }
.cl-loading  { padding: 32px; text-align: center; color: var(--t3, var(--t-muted)); font-size: 13px; }

/* ── Table ── */
.cl-table-wrap { flex: 1; overflow: auto; padding: 8px 16px 24px; }
.cl-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  background: white;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(15,23,60,.04);
}
.cl-th, .cl-td {
  padding: 9px 12px;
  border-bottom: 0.5px solid #F1EFE8;
  text-align: left;
  font-size: 12.5px;
  vertical-align: middle;
}
.cl-th {
  position: sticky; top: 0;
  background: var(--bg2, #FAFAFC);
  font-size: 10.5px; letter-spacing: 0.04em; font-weight: 500; color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  cursor: pointer; user-select: none;
  white-space: nowrap;
  z-index: 5;
}
.cl-th:hover { color: var(--t1, #1E2A4A); }
.cl-th-sort  { margin-left: 4px; color: #7F77DD; }
.cl-th-unit  { color: #C8C7C0; margin-left: 4px; font-size: 9px; }
.cl-th-num   { text-align: right; }
.cl-th-sector{ background: rgba(127,119,221,.04); }
.cl-th-name  { min-width: 220px; }

.cl-tr { transition: background 120ms; cursor: pointer; }
.cl-tr:hover { background: rgba(127,119,221,.04); }
.cl-tr:last-child .cl-td { border-bottom: none; }
.cl-td-num   { text-align: right; font-variant-numeric: tabular-nums; }
.cl-td-sector{ background: rgba(127,119,221,.03); }
.cl-td-name  { font-weight: 500; }

.cl-co-name  { display: flex; flex-direction: column; gap: 1px; }
.cl-co-short { font-size: 13px; color: var(--t1, #1E2A4A); font-weight: 500; }
.cl-co-sector{ font-size: 10px; color: var(--t3, var(--t-muted)); }

.cl-empty { padding: 32px; text-align: center; color: var(--t3, var(--t-muted)); font-size: 12px; }

/* ── Buttons ── */
.cl-btn { padding: 7px 14px; border-radius: 8px; font-size: 12px; font-weight: 500; cursor: pointer; border: 1px solid transparent; transition: all 150ms; }
.cl-btn-secondary { background: white; color: var(--t1, #1E2A4A); border-color: var(--border-hard); }
.cl-btn-secondary:hover:not(:disabled) { background: rgba(15,23,60,.04); }
.cl-btn-secondary:disabled { opacity: .55; cursor: not-allowed; }
.cl-btn-primary   { background: #7F77DD; color: white; }
.cl-btn-primary:hover:not(:disabled) { background: var(--p-deep); }
.cl-btn-primary:disabled { opacity: .55; cursor: not-allowed; }
</style>
