<template>
  <Teleport to="body">
    <Transition name="uza-modal" appear>
      <div v-if="modelValue" class="pa-edit-back" @click.self="close">
        <div class="pa-edit-modal" role="dialog" aria-modal="true">
          <header class="pa-edit-head">
            <div>
              <div class="pa-edit-eyebrow">Procurement editor</div>
              <h2 class="pa-edit-title">Редактирование закупок</h2>
              <p class="pa-edit-sub">
                {{ year ? `Год ${year} · ` : "" }}{{ rows.length }} строк ·
                клик по ячейке → редактирование · Enter — сохранить
              </p>
            </div>
            <button class="pa-edit-x" @click="close" aria-label="Закрыть">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                   stroke="currentColor" stroke-width="2"
                   stroke-linecap="round" stroke-linejoin="round">
                <path d="M18 6L6 18M6 6l12 12"/>
              </svg>
            </button>
          </header>

          <div class="pa-edit-toolbar">
            <input
              v-model="filterQuery"
              type="text"
              placeholder="Поиск: компания / поставщик / продукт / код…"
              class="pa-edit-search"
            />
            <span class="pa-edit-status">
              <template v-if="savingId">Сохранение…</template>
              <template v-else-if="lastSaved">✓ сохранено: {{ lastSavedShort }}</template>
              <template v-else>—</template>
            </span>
          </div>

          <div class="pa-edit-body">
            <table class="pa-edit-table">
              <thead>
                <tr>
                  <th class="num">№</th>
                  <th>Компания</th>
                  <th>Поставщик</th>
                  <th>Продукт</th>
                  <th class="num">Кол-во</th>
                  <th class="num">Цена</th>
                  <th class="num">Сумма</th>
                  <th>Дата</th>
                  <th class="num">Откл. %</th>
                  <th class="ctr">Dirty</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(r, idx) in visibleRows" :key="r.id">
                  <td class="num">{{ idx + 1 }}</td>
                  <td class="nm">{{ r.company_name }}</td>
                  <td>
                    <input
                      class="pa-cell"
                      :value="r.supplier_name || ''"
                      :disabled="!canEdit"
                      @change="patch(r, { supplier_name: $event.target.value })"
                    />
                  </td>
                  <td>
                    <input
                      class="pa-cell"
                      :value="r.product_name || ''"
                      :disabled="!canEdit"
                      @change="patch(r, { product_name: $event.target.value })"
                    />
                  </td>
                  <td class="num">
                    <input
                      class="pa-cell num"
                      type="number"
                      step="0.01"
                      :value="r.quantity ?? ''"
                      :disabled="!canEdit"
                      @change="patch(r, { quantity: parseFloat($event.target.value) || null })"
                    />
                  </td>
                  <td class="num">
                    <input
                      class="pa-cell num"
                      type="number"
                      step="0.01"
                      :value="r.unit_price ?? ''"
                      :disabled="!canEdit"
                      @change="patch(r, { unit_price: parseFloat($event.target.value) || null })"
                    />
                  </td>
                  <td class="num neu">{{ fmt(r.total_uzs) }}</td>
                  <td>
                    <input
                      class="pa-cell"
                      type="date"
                      :value="r.closure_date || ''"
                      :disabled="!canEdit"
                      @change="patch(r, { closure_date: $event.target.value || null })"
                    />
                  </td>
                  <td class="num" :class="r.deviation_pct >= 0 ? 'up' : 'dn'">
                    {{ r.deviation_pct == null ? "—" : (r.deviation_pct >= 0 ? "+" : "") + r.deviation_pct.toFixed(1) }}
                  </td>
                  <td class="ctr">
                    <input
                      type="checkbox"
                      :checked="!!r.is_dirty"
                      :disabled="!canEdit"
                      @change="patch(r, { is_dirty: $event.target.checked })"
                    />
                  </td>
                </tr>
                <tr v-if="!visibleRows.length">
                  <td colspan="10" class="pa-edit-empty">Нет строк по фильтру</td>
                </tr>
              </tbody>
            </table>
          </div>

          <footer class="pa-edit-foot">
            <span class="pa-edit-foot-l">
              Показано <b>{{ visibleRows.length }}</b> из {{ rows.length }} ·
              изменения сохраняются автоматически по PUT /procurement/closures/&lbrace;id&rbrace;
            </span>
            <button class="pa-edit-close" @click="close">Закрыть</button>
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed } from "vue";
import { api } from "@/api/client";
import { useToast } from "@/composables/useToast";
import type { ClosureRow } from "@/api/procurement_analysis";

const props = defineProps<{
  modelValue: boolean;
  rows: ClosureRow[];
  year: number | null;
  canEdit: boolean;
}>();
const emit = defineEmits<{
  "update:modelValue": [v: boolean];
  saved: [];
}>();

const filterQuery = ref("");
const savingId = ref<string | null>(null);
const lastSaved = ref<{ id: string; at: number } | null>(null);

const visibleRows = computed(() => {
  const q = filterQuery.value.trim().toLowerCase();
  if (!q) return props.rows;
  return props.rows.filter((r) => {
    const hay = [
      r.company_name, r.supplier_name, r.product_name, r.product_code,
      r.category_label,
    ].filter(Boolean).join(" ").toLowerCase();
    return hay.includes(q);
  });
});

const lastSavedShort = computed(() => {
  if (!lastSaved.value) return "";
  const sec = Math.max(0, Math.floor((Date.now() - lastSaved.value.at) / 1000));
  return sec < 5 ? "только что" : `${sec}s назад`;
});

function fmt(n: number | null | undefined): string {
  if (n == null) return "—";
  return new Intl.NumberFormat("ru-RU").format(Math.round(Number(n)));
}

async function patch(row: ClosureRow, body: Record<string, unknown>) {
  if (!props.canEdit) return;
  savingId.value = row.id;
  try {
    await api.put(`/procurement/closures/${row.id}`, body);
    // Apply patch optimistically
    Object.assign(row, body);
    lastSaved.value = { id: row.id, at: Date.now() };
    emit("saved");
  } catch (e) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    const detail = err?.response?.data?.detail || err?.message || "—";
    useToast().error("Ошибка сохранения закупки: " + detail);
  } finally {
    savingId.value = null;
  }
}

function close() { emit("update:modelValue", false); }
</script>

<style scoped>
.pa-edit-back {
  position: fixed; inset: 0;
  background: rgba(15, 18, 40, .45);
  -webkit-backdrop-filter: blur(8px);
          backdrop-filter: blur(8px);
  z-index: 9999;
  display: grid;
  place-items: center;
  padding: 24px;
}
.pa-edit-modal {
  width: min(1280px, 100%);
  max-height: calc(100vh - 48px);
  background: var(--card-bg, rgba(255, 255, 255, 0.86));
  backdrop-filter: blur(20px) saturate(1.4);
  -webkit-backdrop-filter: blur(20px) saturate(1.4);
  border: 1px solid var(--card-border, transparent);
  border-radius: 14px;
  box-shadow: 0 24px 64px rgba(15, 23, 60, .20), 0 8px 24px rgba(15, 23, 60, .10);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.pa-edit-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 18px 22px 14px;
  border-bottom: 1px solid rgba(15, 23, 60, .08);
}
.pa-edit-eyebrow {
  font-size: 9.5px;
  font-weight: 500;
  letter-spacing: .07em;
  text-transform: uppercase;
  color: #7F77DD;
}
.pa-edit-title {
  margin: 4px 0 0;
  font-size: 15px;
  font-weight: 500;
  color: var(--t1, #1e2a4a);
  letter-spacing: -.01em;
}
.pa-edit-sub {
  margin: 4px 0 0;
  font-size: 11px;
  color: rgba(15, 23, 60, .55);
}
.pa-edit-x {
  border: 0;
  background: transparent;
  cursor: pointer;
  width: 30px; height: 30px;
  border-radius: 8px;
  display: grid; place-items: center;
  color: rgba(30, 42, 74, .6);
  transition: all .15s;
}
.pa-edit-x:hover { background: rgba(127, 119, 221, .08); color: #7F77DD; }

.pa-edit-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 22px;
  border-bottom: 1px solid rgba(15, 23, 60, .06);
  background: var(--bg2, #FAFAFD);
}
.pa-edit-search {
  flex: 1;
  padding: 8px 12px;
  font: inherit;
  font-size: 12px;
  border: 1px solid rgba(15, 23, 60, .12);
  border-radius: 8px;
  background: var(--bg1, #fff);
  outline: none;
  color: var(--t1, #1e2a4a);
}
.pa-edit-search:focus { border-color: #7F77DD; box-shadow: 0 0 0 3px rgba(127, 119, 221, .14); }
.pa-edit-status {
  font-size: 11px;
  color: rgba(15, 23, 60, .55);
  min-width: 140px;
  text-align: right;
}

.pa-edit-body {
  flex: 1;
  overflow: auto;
  padding: 0;
}
.pa-edit-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11.5px;
  font-variant-numeric: tabular-nums;
}
.pa-edit-table thead th {
  font-size: 9.5px;
  font-weight: 500;
  letter-spacing: .07em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, .55);
  text-align: left;
  padding: 10px 8px;
  background: var(--bg1, #fff);
  border-bottom: 1px solid rgba(15, 23, 60, .08);
  position: sticky;
  top: 0;
  z-index: 1;
}
.pa-edit-table th.num, .pa-edit-table td.num { text-align: right; }
.pa-edit-table th.ctr, .pa-edit-table td.ctr { text-align: center; }
.pa-edit-table tbody td {
  padding: 6px 8px;
  border-bottom: 1px solid rgba(15, 23, 60, .04);
  color: var(--t1, #1e2a4a);
}
.pa-edit-table tbody td.nm { font-weight: 500; }
.pa-edit-table tbody td.neu { color: rgba(15, 23, 60, .65); }
.pa-edit-table tbody td.up { color: #C53030; font-weight: 500; }
.pa-edit-table tbody td.dn { color: #0F6E56; font-weight: 500; }

.pa-cell {
  width: 100%;
  padding: 5px 7px;
  font: inherit;
  font-size: 11.5px;
  border: 1px solid transparent;
  border-radius: 5px;
  background: transparent;
  color: inherit;
  outline: none;
  font-variant-numeric: tabular-nums;
}
.pa-cell.num { text-align: right; }
.pa-cell:hover:not(:disabled) { background: rgba(127, 119, 221, .04); }
.pa-cell:focus { background: var(--bg1, #fff); border-color: #7F77DD; box-shadow: 0 0 0 2px rgba(127, 119, 221, .14); }
.pa-cell:disabled { cursor: not-allowed; opacity: .6; }

.pa-edit-empty {
  text-align: center !important;
  padding: 30px !important;
  color: rgba(15, 23, 60, .35);
  font-style: italic;
}

.pa-edit-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 22px;
  border-top: 1px solid rgba(15, 23, 60, .08);
  background: var(--bg2, #FAFAFD);
}
.pa-edit-foot-l {
  font-size: 10.5px;
  color: rgba(15, 23, 60, .55);
}
.pa-edit-foot-l b { color: var(--t1, #1e2a4a); }
.pa-edit-close {
  padding: 7px 16px;
  font-size: 12px;
  font-weight: 500;
  border: 1px solid rgba(15, 23, 60, .12);
  background: var(--bg1, #fff);
  color: var(--t1, #1e2a4a);
  border-radius: 8px;
  cursor: pointer;
}
.pa-edit-close:hover { background: rgba(127, 119, 221, .06); border-color: #7F77DD; color: #7F77DD; }
</style>
