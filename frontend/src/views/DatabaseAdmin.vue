<script setup lang="ts">
/**
 * DatabaseAdmin — pgAdmin-style DB console для is_owner || is_admin.
 *
 * 3 вкладки:
 *  - Схема:      tree таблиц + детали (колонки/индексы/FK/PK)
 *  - Просмотр:   пагинированный grid строк выбранной таблицы (Browse)
 *  - SQL:        textarea для произвольного SQL + result grid
 *
 * Backend: /admin/db/* (см. backend/app/api/routes/db_admin.py)
 * Audit:   каждый запрос пишется в audit_log.
 */
import { computed, ref, watch, onMounted } from "vue";
import { dbAdminApi, formatBytes, formatNumber } from "@/api/dbAdmin";
import type { SchemaOverview, TableInfo, QueryResponse, TableRowsResponse } from "@/api/dbAdmin";

type Tab = "schema" | "browse" | "sql";

const activeTab = ref<Tab>("schema");

// ────────── Schema ──────────
const schema = ref<SchemaOverview | null>(null);
const schemaLoading = ref(false);
const schemaError = ref<string | null>(null);
const selectedTable = ref<TableInfo | null>(null);
const tableSearch = ref("");

const filteredTables = computed(() => {
  if (!schema.value) return [];
  const q = tableSearch.value.trim().toLowerCase();
  if (!q) return schema.value.tables;
  return schema.value.tables.filter(t => t.name.toLowerCase().includes(q));
});

async function loadSchema() {
  schemaLoading.value = true;
  schemaError.value = null;
  try {
    schema.value = await dbAdminApi.schema();
    if (!selectedTable.value && schema.value.tables.length) {
      selectedTable.value = schema.value.tables[0];
    }
  } catch (e: any) {
    schemaError.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить схему";
  } finally {
    schemaLoading.value = false;
  }
}

function pickTable(t: TableInfo) {
  selectedTable.value = t;
  if (activeTab.value === "browse") {
    loadBrowse(t.name);
  }
}

// ────────── Browse ──────────
const browseData = ref<TableRowsResponse | null>(null);
const browseLoading = ref(false);
const browseError = ref<string | null>(null);
const browseOffset = ref(0);
const browseLimit = ref(50);
const browseOrderBy = ref<string | null>(null);
const browseOrderDir = ref<"ASC" | "DESC">("ASC");

async function loadBrowse(name?: string) {
  const t = name || selectedTable.value?.name;
  if (!t) return;
  browseLoading.value = true;
  browseError.value = null;
  try {
    browseData.value = await dbAdminApi.browseTable(t, {
      limit: browseLimit.value,
      offset: browseOffset.value,
      order_by: browseOrderBy.value ?? undefined,
      order_dir: browseOrderDir.value,
    });
  } catch (e: any) {
    browseError.value = e?.response?.data?.detail || e?.message || "Ошибка загрузки строк";
  } finally {
    browseLoading.value = false;
  }
}

function browsePage(delta: number) {
  browseOffset.value = Math.max(0, browseOffset.value + delta * browseLimit.value);
  loadBrowse();
}

function browseSort(col: string) {
  if (browseOrderBy.value === col) {
    browseOrderDir.value = browseOrderDir.value === "ASC" ? "DESC" : "ASC";
  } else {
    browseOrderBy.value = col;
    browseOrderDir.value = "ASC";
  }
  browseOffset.value = 0;
  loadBrowse();
}

watch(activeTab, (tab) => {
  if (tab === "browse" && !browseData.value && selectedTable.value) {
    loadBrowse();
  }
});

// ────────── SQL Console ──────────
const sqlText = ref("SELECT current_database(), version(), now();");
const sqlResult = ref<QueryResponse | null>(null);
const sqlError = ref<string | null>(null);
const sqlBusy = ref(false);

const sqlIsDestructive = computed(() => {
  const s = sqlText.value.toUpperCase();
  return /\b(DROP|TRUNCATE|DELETE|ALTER|GRANT|REVOKE)\b/.test(s);
});

async function runSql(dryRun = false) {
  if (!sqlText.value.trim()) return;

  if (sqlIsDestructive.value && !dryRun) {
    const ok = confirm(
      "ВНИМАНИЕ: запрос содержит destructive команды (DROP/TRUNCATE/DELETE/ALTER/GRANT/REVOKE).\n\n" +
      "Это необратимая операция. Продолжить?",
    );
    if (!ok) return;
  }

  sqlBusy.value = true;
  sqlError.value = null;
  try {
    sqlResult.value = await dbAdminApi.query(sqlText.value, dryRun);
  } catch (e: any) {
    sqlError.value = e?.response?.data?.detail || e?.message || "Ошибка SQL";
    sqlResult.value = null;
  } finally {
    sqlBusy.value = false;
  }
}

function insertSelectFrom(t: TableInfo) {
  sqlText.value = `SELECT * FROM "${t.name}" LIMIT 100;`;
  activeTab.value = "sql";
}

function exportCsv() {
  if (!sqlResult.value) return;
  const r = sqlResult.value;
  const header = r.columns.map(csvCell).join(",");
  const lines = r.rows.map((row) => row.map(csvCell).join(","));
  const blob = new Blob(["﻿" + [header, ...lines].join("\n")], {
    type: "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `query_${Date.now()}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

function csvCell(v: any): string {
  if (v === null || v === undefined) return "";
  const s = typeof v === "object" ? JSON.stringify(v) : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function fmtCell(v: any): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "✓" : "✗";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

onMounted(loadSchema);
</script>

<template>
  <div class="dba-page">
    <!-- Header -->
    <div class="dba-header">
      <div class="dba-title-row">
        <div>
          <div class="dba-eyebrow">ADMIN · INFRASTRUCTURE</div>
          <h1 class="dba-title">Консоль базы данных</h1>
          <div class="dba-sub">
            Прямой доступ к PostgreSQL · все операции пишутся в audit_log
          </div>
        </div>
        <div v-if="schema" class="dba-meta">
          <div><span class="dba-meta-label">Размер БД:</span> {{ formatBytes(schema.db_size_bytes) }}</div>
          <div><span class="dba-meta-label">Таблиц:</span> {{ schema.tables.length }}</div>
          <div v-if="schema.db_version" class="dba-meta-ver">{{ schema.db_version.split(" ").slice(0, 2).join(" ") }}</div>
        </div>
      </div>

      <!-- Tabs -->
      <div class="dba-tabs">
        <button
          v-for="t in (['schema', 'browse', 'sql'] as Tab[])"
          :key="t"
          class="dba-tab"
          :class="{ 'is-active': activeTab === t }"
          @click="activeTab = t"
        >
          {{ t === "schema" ? "Схема" : t === "browse" ? "Просмотр" : "SQL-консоль" }}
        </button>
      </div>
    </div>

    <!-- ────── Schema ────── -->
    <div v-if="activeTab === 'schema'" class="dba-pane dba-pane-split">
      <!-- Sidebar tree -->
      <aside class="dba-sidebar">
        <input
          v-model="tableSearch"
          class="dba-search"
          placeholder="Поиск таблицы…"
          type="text"
        />
        <div class="dba-tree">
          <div v-if="schemaLoading" class="dba-loading">Загрузка…</div>
          <div v-else-if="schemaError" class="dba-error">{{ schemaError }}</div>
          <div
            v-for="t in filteredTables"
            :key="`${t.schema}.${t.name}`"
            class="dba-tree-item"
            :class="{ 'is-active': selectedTable?.name === t.name }"
            @click="pickTable(t)"
          >
            <div class="dba-tree-name">{{ t.name }}</div>
            <div class="dba-tree-meta">
              {{ formatNumber(t.row_count) }} · {{ formatBytes(t.size_bytes) }}
            </div>
          </div>
        </div>
      </aside>

      <!-- Detail -->
      <main class="dba-detail">
        <template v-if="selectedTable">
          <div class="dba-detail-head">
            <h2 class="dba-detail-title">{{ selectedTable.name }}</h2>
            <div class="dba-detail-actions">
              <button class="dba-btn" @click="activeTab = 'browse'; loadBrowse(selectedTable.name)">
                Просмотр строк →
              </button>
              <button class="dba-btn dba-btn-secondary" @click="insertSelectFrom(selectedTable)">
                SELECT * в консоль →
              </button>
            </div>
          </div>

          <section class="dba-section">
            <h3>Колонки ({{ selectedTable.columns.length }})</h3>
            <table class="dba-table">
              <thead>
                <tr>
                  <th>Имя</th>
                  <th>Тип</th>
                  <th>NULL</th>
                  <th>Default</th>
                  <th>Ключи</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="c in selectedTable.columns" :key="c.name">
                  <td class="dba-mono">
                    {{ c.name }}
                  </td>
                  <td class="dba-mono dba-type">
                    {{ c.data_type }}<span v-if="c.character_maximum_length">({{ c.character_maximum_length }})</span>
                  </td>
                  <td>{{ c.is_nullable ? "yes" : "—" }}</td>
                  <td class="dba-mono dba-default">{{ c.column_default || "—" }}</td>
                  <td>
                    <span v-if="c.is_pk" class="dba-pill dba-pill-pk">PK</span>
                    <span v-if="c.is_fk" class="dba-pill dba-pill-fk" :title="c.fk_references || ''">FK</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </section>

          <section class="dba-section" v-if="selectedTable.indexes.length">
            <h3>Индексы ({{ selectedTable.indexes.length }})</h3>
            <table class="dba-table">
              <thead>
                <tr>
                  <th>Имя</th>
                  <th>Тип</th>
                  <th>Определение</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="i in selectedTable.indexes" :key="i.name">
                  <td class="dba-mono">{{ i.name }}</td>
                  <td>
                    <span v-if="i.is_primary" class="dba-pill dba-pill-pk">PRIMARY</span>
                    <span v-else-if="i.is_unique" class="dba-pill dba-pill-fk">UNIQUE</span>
                    <span v-else class="dba-pill">INDEX</span>
                  </td>
                  <td class="dba-mono dba-def">{{ i.definition }}</td>
                </tr>
              </tbody>
            </table>
          </section>
        </template>
        <div v-else class="dba-empty">Выберите таблицу слева</div>
      </main>
    </div>

    <!-- ────── Browse ────── -->
    <div v-else-if="activeTab === 'browse'" class="dba-pane">
      <div class="dba-browse-header">
        <h2 v-if="selectedTable">Просмотр: <span class="dba-mono">{{ selectedTable.name }}</span></h2>
        <h2 v-else>Выберите таблицу во вкладке «Схема»</h2>
        <div class="dba-browse-controls" v-if="selectedTable">
          <button class="dba-btn dba-btn-secondary" @click="loadBrowse()" :disabled="browseLoading">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;margin-right:5px"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>Обновить
          </button>
          <select v-model.number="browseLimit" @change="browseOffset = 0; loadBrowse()" class="dba-select">
            <option :value="25">25 / стр</option>
            <option :value="50">50 / стр</option>
            <option :value="100">100 / стр</option>
            <option :value="500">500 / стр</option>
            <option :value="1000">1000 / стр</option>
          </select>
        </div>
      </div>

      <div v-if="browseError" class="dba-error">{{ browseError }}</div>
      <div v-else-if="browseLoading" class="dba-loading">Загрузка…</div>
      <template v-else-if="browseData">
        <div class="dba-browse-stats">
          Всего: <b>{{ formatNumber(browseData.total) }}</b> ·
          Показано {{ browseOffset + 1 }}–{{ Math.min(browseOffset + browseData.rows.length, browseData.total) }}
        </div>
        <div class="dba-grid-wrap">
          <table class="dba-grid">
            <thead>
              <tr>
                <th
                  v-for="c in browseData.columns"
                  :key="c"
                  class="dba-mono dba-grid-th"
                  @click="browseSort(c)"
                >
                  {{ c }}
                  <span v-if="browseOrderBy === c">{{ browseOrderDir === "ASC" ? "↑" : "↓" }}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, ri) in browseData.rows" :key="ri">
                <td v-for="c in browseData.columns" :key="c" class="dba-mono dba-grid-td" :title="fmtCell(row[c])">
                  {{ fmtCell(row[c]).slice(0, 200) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="dba-pager">
          <button class="dba-btn dba-btn-secondary" :disabled="browseOffset === 0" @click="browsePage(-1)">← Назад</button>
          <button
            class="dba-btn dba-btn-secondary"
            :disabled="browseOffset + browseLimit >= browseData.total"
            @click="browsePage(1)"
          >
            Вперёд →
          </button>
        </div>
      </template>
    </div>

    <!-- ────── SQL Console ────── -->
    <div v-else class="dba-pane">
      <div class="dba-sql-toolbar">
        <button class="dba-btn dba-btn-primary" @click="runSql(false)" :disabled="sqlBusy">
          ▶ Выполнить
        </button>
        <button class="dba-btn dba-btn-secondary" @click="runSql(true)" :disabled="sqlBusy" title="Откатывает транзакцию после запроса">
          ▷ Dry-run
        </button>
        <button v-if="sqlResult" class="dba-btn dba-btn-secondary" @click="exportCsv">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;margin-right:5px"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>Экспорт CSV
        </button>
        <span v-if="sqlIsDestructive" class="dba-warn">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;margin-right:4px"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>Запрос содержит destructive команды
        </span>
        <span v-if="sqlResult" class="dba-meta-stat">
          {{ sqlResult.command }} · {{ formatNumber(sqlResult.row_count) }} строк ·
          {{ sqlResult.duration_ms }} ms
          <span v-if="sqlResult.truncated" class="dba-warn"> · обрезано до 10000</span>
        </span>
      </div>

      <textarea
        v-model="sqlText"
        class="dba-sql-editor"
        spellcheck="false"
        @keydown.ctrl.enter.prevent="runSql(false)"
        @keydown.meta.enter.prevent="runSql(false)"
        placeholder="SELECT * FROM users LIMIT 10;"
      />

      <div v-if="sqlError" class="dba-error dba-sql-error">{{ sqlError }}</div>

      <div v-else-if="sqlResult" class="dba-grid-wrap dba-sql-result">
        <table v-if="sqlResult.columns.length" class="dba-grid">
          <thead>
            <tr>
              <th v-for="c in sqlResult.columns" :key="c" class="dba-mono dba-grid-th">{{ c }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, ri) in sqlResult.rows" :key="ri">
              <td v-for="(v, ci) in row" :key="ci" class="dba-mono dba-grid-td" :title="fmtCell(v)">
                {{ fmtCell(v).slice(0, 200) }}
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="dba-empty">
          Команда выполнена. Affected rows: {{ sqlResult.row_count }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dba-page {
  padding: 16px 22px 28px;
  font-family: var(--font, system-ui);
  background: #F4F3F9;
  min-height: 100vh;
}

/* Header */
.dba-header {
  background: #fff;
  border-radius: 14px;
  padding: 18px 22px 0;
  box-shadow: 0 1px 0 rgba(15, 23, 60, 0.06), 0 12px 32px rgba(15, 23, 60, 0.06);
  margin-bottom: 14px;
}
.dba-title-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 24px;
  padding-bottom: 14px;
}
.dba-eyebrow {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: #888780;
  margin-bottom: 4px;
}
.dba-title {
  font-size: 22px;
  font-weight: 500;
  color: #1E2A4A;
  letter-spacing: -0.015em;
  margin: 0 0 4px 0;
}
.dba-sub {
  font-size: 12px;
  color: #888780;
}
.dba-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: #51596F;
  text-align: right;
}
.dba-meta-label { color: #888780; }
.dba-meta-ver { font-size: 11px; color: #B0B0AA; }

/* Tabs */
.dba-tabs {
  display: flex;
  gap: 4px;
  padding-top: 2px;
}
.dba-tab {
  background: none;
  border: none;
  padding: 10px 16px;
  font-size: 12.5px;
  font-weight: 500;
  color: #888780;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: color 0.15s, border-color 0.15s;
  font-family: inherit;
}
.dba-tab:hover { color: #534AB7; }
.dba-tab.is-active {
  color: #1E2A4A;
  border-bottom-color: #7F77DD;
}

/* Pane */
.dba-pane {
  background: #fff;
  border-radius: 14px;
  padding: 18px 22px;
  box-shadow: 0 1px 0 rgba(15, 23, 60, 0.06), 0 12px 32px rgba(15, 23, 60, 0.06);
}
.dba-pane-split {
  display: grid;
  grid-template-columns: 260px 1fr;
  gap: 18px;
  padding: 0;
}

/* Sidebar */
.dba-sidebar {
  padding: 14px;
  border-right: 1px solid #EFEEF4;
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: calc(100vh - 220px);
}
.dba-search {
  font-family: inherit;
  font-size: 12.5px;
  padding: 8px 12px;
  border: 1px solid #E5E5EA;
  border-radius: 8px;
  outline: none;
}
.dba-search:focus { border-color: #7F77DD; }
.dba-tree {
  overflow-y: auto;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.dba-tree-item {
  padding: 8px 10px;
  border-radius: 7px;
  cursor: pointer;
  transition: background 0.12s;
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
}
.dba-tree-item:hover { background: #F6F5FB; }
.dba-tree-item.is-active { background: rgba(127, 119, 221, 0.12); }
.dba-tree-name {
  font-size: 12.5px;
  color: #1E2A4A;
  font-weight: 500;
}
.dba-tree-meta {
  font-size: 10.5px;
  color: #888780;
  margin-top: 2px;
}

/* Detail */
.dba-detail { padding: 18px 22px; overflow-y: auto; max-height: calc(100vh - 220px); }
.dba-detail-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 18px;
  padding-bottom: 14px;
  border-bottom: 1px solid #EFEEF4;
}
.dba-detail-title {
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-size: 18px;
  font-weight: 600;
  color: #1E2A4A;
  margin: 0;
}
.dba-detail-actions { display: flex; gap: 8px; }
.dba-section { margin-bottom: 24px; }
.dba-section h3 {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #888780;
  margin: 0 0 10px 0;
}

/* Tables */
.dba-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}
.dba-table thead {
  background: #FAFAFC;
}
.dba-table th {
  padding: 8px 10px;
  text-align: left;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #888780;
  border-bottom: 1px solid #EFEEF4;
}
.dba-table td {
  padding: 8px 10px;
  border-bottom: 1px solid #F4F3F9;
  color: #1E2A4A;
}
.dba-table tr:hover td { background: #FAFAFC; }
.dba-mono { font-family: ui-monospace, "SF Mono", Menlo, monospace; }
.dba-type { color: #4A4F66; font-size: 11.5px; }
.dba-default { color: #888780; font-size: 11px; }
.dba-def { font-size: 10.5px; color: #51596F; }

/* Pills */
.dba-pill {
  display: inline-block;
  padding: 2px 7px;
  font-size: 9px;
  font-weight: 600;
  border-radius: 11px;
  letter-spacing: 0.04em;
  background: #EFEEF4;
  color: #51596F;
  margin-right: 4px;
}
.dba-pill-pk { background: rgba(127, 119, 221, 0.15); color: #534AB7; }
.dba-pill-fk { background: rgba(55, 138, 221, 0.15); color: #1F5DA2; }

/* Browse */
.dba-browse-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}
.dba-browse-header h2 { margin: 0; font-size: 16px; color: #1E2A4A; font-weight: 500; }
.dba-browse-controls { display: flex; gap: 8px; align-items: center; }
.dba-browse-stats {
  font-size: 11.5px;
  color: #888780;
  margin-bottom: 10px;
}
.dba-grid-wrap {
  overflow: auto;
  border: 1px solid #EFEEF4;
  border-radius: 8px;
  max-height: 60vh;
}
.dba-grid {
  width: 100%;
  border-collapse: collapse;
  font-size: 11.5px;
}
.dba-grid-th {
  position: sticky;
  top: 0;
  background: #FAFAFC;
  padding: 8px 10px;
  text-align: left;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #51596F;
  border-bottom: 1px solid #EFEEF4;
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}
.dba-grid-th:hover { background: #F4F3F9; }
.dba-grid-td {
  padding: 6px 10px;
  border-bottom: 1px solid #F8F7FB;
  white-space: nowrap;
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #1E2A4A;
}
.dba-pager { display: flex; gap: 8px; justify-content: flex-end; margin-top: 10px; }

/* SQL */
.dba-sql-toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.dba-sql-editor {
  width: 100%;
  min-height: 180px;
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-size: 12.5px;
  padding: 12px 14px;
  border: 1px solid #E5E5EA;
  border-radius: 8px;
  outline: none;
  resize: vertical;
  background: #FAFAFC;
  color: #1E2A4A;
  line-height: 1.5;
}
.dba-sql-editor:focus { border-color: #7F77DD; background: #fff; }
.dba-sql-result { margin-top: 14px; }
.dba-sql-error { margin-top: 14px; }
.dba-warn { font-size: 11px; color: #C36868; font-weight: 500; }
.dba-meta-stat { font-size: 11.5px; color: #51596F; margin-left: auto; }

/* Buttons */
.dba-btn {
  background: #fff;
  color: #1E2A4A;
  border: 1px solid #E5E5EA;
  border-radius: 7px;
  font-size: 11.5px;
  font-weight: 500;
  padding: 7px 14px;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.15s;
}
.dba-btn:hover { background: #FAFAFC; border-color: #D5D5DA; }
.dba-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.dba-btn-primary {
  background: #7F77DD;
  color: #fff;
  border-color: #7F77DD;
}
.dba-btn-primary:hover { background: #534AB7; border-color: #534AB7; }
.dba-btn-secondary { background: #FAFAFC; }
.dba-select {
  font-family: inherit;
  font-size: 11.5px;
  padding: 7px 8px;
  border: 1px solid #E5E5EA;
  border-radius: 7px;
  background: #fff;
}

/* States */
.dba-loading, .dba-empty {
  padding: 40px 20px;
  text-align: center;
  color: #888780;
  font-size: 13px;
}
.dba-error {
  padding: 16px;
  background: rgba(226, 75, 74, 0.08);
  border: 1px solid rgba(226, 75, 74, 0.25);
  border-radius: 8px;
  color: #C36868;
  font-size: 12.5px;
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
}
</style>
