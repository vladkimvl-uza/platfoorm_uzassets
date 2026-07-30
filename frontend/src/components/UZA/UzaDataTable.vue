<script setup lang="ts" generic="T extends Record<string, any>">
/**
 * UzaDataTable — единая «генерик»-таблица: thead + tbody с консолидированным
 * th/td-стилем (Apple-аудит, консолидация ~60 кустарных таблиц). Кастомные
 * таблицы со встроенной визуализацией (heatmap / league / editable-grid /
 * матрицы rowspan) НЕ мигрируются сюда — у них своя разметка.
 *
 * Колонки — конфигом; ячейки по умолчанию рендерят row[col.key], кастом —
 * через слот #cell-<key>={ row, value, index }. Заголовок — #head-<key>.
 * Сортировка: клик по th (col.sortable) → asc → desc → off, по сырому row[key].
 * Пустое состояние — слот #empty (или дефолтный текст emptyText).
 *
 * Стили берут токены --fs- и --r-; цвета — через var(...) с фолбэками.
 */
import { computed, ref } from "vue";
import { i18nKey } from "@/locale/keys";
import { useI18n } from "@/composables/useI18n";
import { getCurrentIntlLocale } from "@/locale/i18n";
const { t } = useI18n();



interface Column<R> {
  key: string;
  label?: string;
  align?: "start" | "center" | "end";
  width?: string;
  sortable?: boolean;
  mono?: boolean;       // tabular-nums + mono-подобный кегль (числа/коды)
  nowrap?: boolean;
  /** аксессор для сортировки, если row[key] не подходит */
  sortAccessor?: (row: R) => string | number | null | undefined;
}

const props = withDefaults(defineProps<{
  columns: Column<T>[];
  rows: T[];
  rowKey?: string | ((row: T, index: number) => string | number);
  clickableRows?: boolean;
  stickyHead?: boolean;
  dense?: boolean;
  emptyText?: string;
}>(), {
  rowKey: "id",
  emptyText: i18nKey("Нет данных"),
});

const emit = defineEmits<{ "row-click": [T] }>();

const sortKey = ref<string | null>(null);
const sortDir = ref<"asc" | "desc">("asc");

function toggleSort(col: Column<T>) {
  if (!col.sortable) return;
  if (sortKey.value !== col.key) { sortKey.value = col.key; sortDir.value = "asc"; return; }
  if (sortDir.value === "asc") { sortDir.value = "desc"; return; }
  sortKey.value = null;  // third click → off
}

const sortedRows = computed(() => {
  if (!sortKey.value) return props.rows;
  const col = props.columns.find((c) => c.key === sortKey.value);
  if (!col) return props.rows;
  const acc = col.sortAccessor ?? ((r: T) => r[col.key]);
  const dir = sortDir.value === "asc" ? 1 : -1;
  return [...props.rows].sort((a, b) => {
    const va = acc(a); const vb = acc(b);
    if (va == null && vb == null) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;
    if (typeof va === "number" && typeof vb === "number") return (va - vb) * dir;
    return String(va).localeCompare(String(vb), getCurrentIntlLocale(), { numeric: true }) * dir;
  });
});

function keyFor(row: T, i: number): string | number {
  if (typeof props.rowKey === "function") return props.rowKey(row, i);
  return (row[props.rowKey] as string | number | undefined) ?? i;
}

const colCount = computed(() => props.columns.length);
function ariaSort(col: Column<T>): "ascending" | "descending" | "none" | undefined {
  if (!col.sortable) return undefined;
  if (sortKey.value !== col.key) return "none";
  return sortDir.value === "asc" ? "ascending" : "descending";
}
</script>

<template>
  <div class="udt-wrap">
    <table class="udt" :class="{ 'udt-dense': dense, 'udt-sticky': stickyHead }">
      <thead>
        <tr>
          <th
            v-for="col in columns"
            :key="col.key"
            :class="[`al-${col.align || 'start'}`, { 'is-sortable': col.sortable, 'is-sorted': sortKey === col.key }]"
            :style="col.width ? { width: col.width } : undefined"
            :aria-sort="ariaSort(col)"
            @click="toggleSort(col)"
          >
            <slot :name="`head-${col.key}`" :col="col">
              <span class="udt-th-in">
                {{ col.label ? t(col.label) : "" }}
                <svg v-if="col.sortable" class="udt-sort-ico" :class="{ on: sortKey === col.key, desc: sortKey === col.key && sortDir === 'desc' }"
                     width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" aria-hidden="true">
                  <polyline points="6 15 12 9 18 15" />
                </svg>
              </span>
            </slot>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(row, i) in sortedRows"
          :key="keyFor(row, i)"
          :class="{ 'is-click': clickableRows }"
          :tabindex="clickableRows ? 0 : undefined"
          @click="clickableRows && emit('row-click', row)"
          @keydown.enter="clickableRows && emit('row-click', row)"
        >
          <td
            v-for="col in columns"
            :key="col.key"
            :class="[`al-${col.align || 'start'}`, { 'is-mono': col.mono, 'is-nowrap': col.nowrap }]"
          >
            <slot :name="`cell-${col.key}`" :row="row" :value="row[col.key]" :index="i">
              {{ row[col.key] }}
            </slot>
          </td>
        </tr>
        <tr v-if="!sortedRows.length" class="udt-empty-row">
          <td :colspan="colCount">
            <slot name="empty"><span class="udt-empty">{{ emptyText }}</span></slot>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.udt-wrap { width: 100%; overflow-x: auto; }
.udt {
  width: 100%;
  border-collapse: collapse;
  font-family: var(--font, inherit);
}

.udt thead th {
  text-align: left;
  padding: 8px 11px;
  font-size: var(--fs-2xs, 9px);
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: .06em;
  color: var(--t3, #94a3b8);
  background: var(--bg2, #fafafc);
  border-bottom: 1px solid var(--border, rgba(99, 102, 180, .1));
  white-space: nowrap;
  user-select: none;
}
.udt.udt-sticky thead th { position: sticky; top: 0; z-index: var(--z-sticky, 40); }

.udt tbody td {
  padding: 9px 11px;
  font-size: var(--fs-sm, 11.5px);
  color: var(--t1, #1e2a4a);
  border-bottom: 1px solid var(--border, rgba(15, 23, 60, .05));
  vertical-align: middle;
}
.udt.udt-dense thead th { padding: 6px 9px; }
.udt.udt-dense tbody td { padding: 6px 9px; }

.udt tbody tr.is-click { cursor: pointer; transition: background .12s; }
.udt tbody tr.is-click:hover { background: rgba(124, 111, 247, .04); }
.udt tbody tr.is-click:focus-visible { outline: 2px solid var(--p, #7c6ff7); outline-offset: -2px; }

.al-start { text-align: left; }
.al-center { text-align: center; }
.al-end { text-align: right; }
td.al-center { text-align: center; }
td.al-end { text-align: right; }
.is-mono { font-variant-numeric: tabular-nums; }
.is-nowrap { white-space: nowrap; }

.udt th.is-sortable { cursor: pointer; }
.udt th.is-sortable:hover { color: var(--t2, #5f5e5a); }
.udt-th-in { display: inline-flex; align-items: center; gap: 4px; }
.udt-sort-ico { opacity: 0; transition: opacity .12s, transform .15s var(--ease-standard, ease); }
.udt th.is-sortable:hover .udt-sort-ico { opacity: .5; }
.udt-sort-ico.on { opacity: 1; }
.udt-sort-ico.desc { transform: rotate(180deg); }

.udt-empty-row td { padding: 0; border-bottom: none; }
.udt-empty {
  display: block;
  padding: 32px 16px;
  text-align: center;
  font-size: var(--fs-base, 12.5px);
  font-style: italic;
  color: var(--t3, #94a3b8);
}
</style>
