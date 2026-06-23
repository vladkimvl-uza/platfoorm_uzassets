<script setup lang="ts">
/**
 * IfrsReportHistory — «История отчётности МСФО»: даты публикации МСФО-отчётности
 * по компаниям (строки) × годам (столбцы, с 2022). Inline date-picker, группировка
 * по секторам. Внизу — кто и когда вносил последнее изменение. Только под МСФО.
 */
import { computed, onMounted, ref } from "vue";
import { useToast } from "@/composables/useToast";
import type { CompanyListItem, SectorBrief } from "@/api/companies";
import { ifrsReportHistoryApi, type IfrsHistoryLastChange } from "@/api/ifrsReportHistory";

const props = defineProps<{
  companies: CompanyListItem[];
  sectors: SectorBrief[];
  canEdit?: boolean;
}>();

const toast = useToast();
const loading = ref(true);
const saving = ref(false);

interface Cell { published_on: string | null; updated_by_name: string | null; updated_at: string | null; }
const histMap = ref<Record<string, Record<number, Cell>>>({});
const lastChange = ref<IfrsHistoryLastChange>({ by_name: null, at: null });

// Года: с 2022 по последний ЗАВЕРШЁННЫЙ год (текущий не показываем). Можно добавлять
// вручную кнопкой «+ год»; заполненные годы подхватываются автоматически при загрузке.
const addedMaxYear = ref(0);
const maxDataYear = computed(() => {
  let mx = 0;
  for (const cid of Object.keys(histMap.value)) {
    const co = histMap.value[cid] || {};
    for (const yStr of Object.keys(co)) {
      const y = Number(yStr);
      if (co[y]?.published_on && y > mx) mx = y;
    }
  }
  return mx;
});
const years = computed(() => {
  const baseHi = new Date().getFullYear() - 1;  // текущий год не показываем
  const hi = Math.max(2022, baseHi, maxDataYear.value, addedMaxYear.value);
  const out: number[] = [];
  for (let y = 2022; y <= hi; y++) out.push(y);
  return out;
});
function addYear() {
  addedMaxYear.value = (years.value[years.value.length - 1] || 2025) + 1;
}

// Календарная разница в днях (isoTo − isoFrom). Положительно = isoTo позже.
function daysBetween(isoFrom: string, isoTo: string): number | null {
  const a = isoFrom.match(/^(\d{4})-(\d{2})-(\d{2})/);
  const b = isoTo.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!a || !b) return null;
  const da = Date.UTC(+a[1], +a[2] - 1, +a[3]);
  const db = Date.UTC(+b[1], +b[2] - 1, +b[3]);
  return Math.round((db - da) / 86400000);
}
// Дедлайн публикации МСФО за год Y — 15 июня следующего года
// (эталон: FY2024 → 15.06.2025, из «МСФО отчёты.xlsx»).
function deadlineFor(y: number): string {
  return `${y + 1}-06-15`;
}
// Лаг публикации: дни от 31.12 года отчёта до даты публикации.
function lagDays(cid: string, y: number): number | null {
  const pub = cellDate(cid, y);
  if (!pub) return null;
  return daysBetween(`${y}-12-31`, pub);
}
interface DelayInfo {
  lag: number | null;                      // дни от 31.12(lastY) до публикации
  status: "late" | "ontime" | null;        // относительно дедлайна 15.06(lastY+1)
  improve: number | null;                  // lag(prevY) − lag(lastY); >0 = быстрее
  lastY: number | null;
  prevY: number | null;
}
// По последнему заполненному году: лаг от 31.12, статус vs дедлайн, улучшение к пред. году.
function companyDelay(cid: string): DelayInfo {
  const filled = years.value.filter(y => cellDate(cid, y)).sort((a, b) => b - a);
  if (!filled.length) return { lag: null, status: null, improve: null, lastY: null, prevY: null };
  const lastY = filled[0];
  const pub = cellDate(cid, lastY)!;
  const lag = lagDays(cid, lastY);
  const past = daysBetween(deadlineFor(lastY), pub);  // pub − дедлайн; >0 = позже срока
  const status: "late" | "ontime" = past != null && past > 0 ? "late" : "ontime";
  let improve: number | null = null;
  let prevY: number | null = null;
  if (filled.length >= 2) {
    prevY = filled[1];
    const prevLag = lagDays(cid, prevY);
    if (lag != null && prevLag != null) improve = prevLag - lag;  // >0 = в этом году раньше
  }
  return { lag, status, improve, lastY, prevY };
}
function delayTip(cid: string): string {
  const d = companyDelay(cid);
  if (d.lastY == null) return "Нет заполненных дат";
  const base = `${d.lastY}: лаг ${d.lag} дн. от 31.12.${d.lastY}; дедлайн 15.06.${d.lastY + 1} — ` +
    (d.status === "late" ? "опубликовано позже срока" : "в срок");
  return d.improve != null
    ? `${base}. К ${d.prevY}: ` + (d.improve > 0 ? `быстрее на ${d.improve} дн.` : d.improve < 0 ? `медленнее на ${-d.improve} дн.` : "без изменений")
    : base;
}
const delayMap = computed<Record<string, DelayInfo>>(() => {
  const out: Record<string, DelayInfo> = {};
  for (const g of grouped.value) for (const c of g.companies) out[c.id] = companyDelay(c.id);
  return out;
});

const grouped = computed(() => {
  const order = new Map(props.sectors.map((s, i) => [String(s.code).toLowerCase(), i]));
  const map = new Map<string, { code: string; name: string; color: string; companies: CompanyListItem[] }>();
  for (const c of props.companies) {
    if (c.is_active === false) continue;
    const key = String(c.sector_code || "—").toLowerCase();
    let g = map.get(key);
    if (!g) {
      g = { code: key, name: c.sector_name || "Без сектора", color: c.sector_color || "#94A3B8", companies: [] };
      map.set(key, g);
    }
    g.companies.push(c);
  }
  return Array.from(map.values()).sort((a, b) => (order.get(a.code) ?? 900) - (order.get(b.code) ?? 900));
});

async function loadHistory() {
  loading.value = true;
  try {
    const resp = await ifrsReportHistoryApi.list();
    const m: Record<string, Record<number, Cell>> = {};
    for (const r of resp.rows) {
      if (!m[r.company_id]) m[r.company_id] = {};
      m[r.company_id][r.year] = { published_on: r.published_on, updated_by_name: r.updated_by_name, updated_at: r.updated_at };
    }
    histMap.value = m;
    lastChange.value = resp.last_change || { by_name: null, at: null };
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    toast.error("Не удалось загрузить историю МСФО: " + (err?.response?.data?.detail || err?.message || "ошибка"));
  } finally {
    loading.value = false;
  }
}
onMounted(loadHistory);

function cell(cid: string, y: number): Cell | undefined { return histMap.value[cid]?.[y]; }
function cellDate(cid: string, y: number): string | null { return cell(cid, y)?.published_on ?? null; }

function fmtDate(d: string | null): string {
  if (!d) return "—";
  const m = d.match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[3]}.${m[2]}.${m[1]}` : d;
}
function fmtDT(d: string | null): string {
  if (!d) return "";
  const dt = new Date(d);
  if (isNaN(dt.getTime())) return d;
  return dt.toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}
function cellTip(cid: string, y: number): string {
  const c = cell(cid, y);
  if (!c || (!c.published_on && !c.updated_by_name)) return props.canEdit ? "Нажмите, чтобы задать дату публикации" : "Нет данных";
  const parts: string[] = [];
  if (c.published_on) parts.push("Опубликовано: " + fmtDate(c.published_on));
  if (c.updated_by_name) parts.push("Внёс: " + c.updated_by_name);
  if (c.updated_at) parts.push(fmtDT(c.updated_at));
  return parts.join(" · ");
}

// ─── Inline-редактирование: ручной ввод с авто-маской дд.мм.гггг ──────
const editing = ref<{ cid: string; y: number } | null>(null);
const editVal = ref("");
const editOrig = ref("");

function isEditing(cid: string, y: number): boolean {
  return !!editing.value && editing.value.cid === cid && editing.value.y === y;
}
// Маска: вводятся только цифры (ддммгггг), точки проставляются автоматически.
function maskDate(raw: string): string {
  const d = raw.replace(/\D/g, "").slice(0, 8);
  let out = d.slice(0, 2);
  if (d.length > 2) out += "." + d.slice(2, 4);
  if (d.length > 4) out += "." + d.slice(4, 8);
  return out;
}
function isoToMasked(iso: string | null): string {
  if (!iso) return "";
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[3]}.${m[2]}.${m[1]}` : "";
}
// Парсим по цифрам — принимаем и «03.03.2026», и просто «03032026».
function parseMasked(s: string): string | null {
  const d = s.replace(/\D/g, "");
  if (d.length !== 8) return null;
  const dd = +d.slice(0, 2), mm = +d.slice(2, 4), yyyy = +d.slice(4, 8);
  if (yyyy < 1900 || yyyy > 2100 || mm < 1 || mm > 12 || dd < 1 || dd > 31) return null;
  const dt = new Date(yyyy, mm - 1, dd);
  if (dt.getFullYear() !== yyyy || dt.getMonth() !== mm - 1 || dt.getDate() !== dd) return null;
  return `${d.slice(4, 8)}-${d.slice(2, 4)}-${d.slice(0, 2)}`;  // YYYY-MM-DD
}
function startEdit(cid: string, y: number) {
  if (!props.canEdit) return;
  editOrig.value = isoToMasked(cellDate(cid, y));
  editVal.value = editOrig.value;
  editing.value = { cid, y };
}
// v-model держит значение; @input докладывает маску (точки проставляются сами).
function onMaskInput() {
  editVal.value = maskDate(editVal.value);
}
// function-ref: просто фокус при появлении (надёжно в v-for; значение — через v-model)
function onDateMounted(el: unknown) {
  if (el && el instanceof HTMLInputElement) el.focus();
}
function closeEdit() { editing.value = null; }

async function commitEdit(cid: string, y: number, explicit = false) {
  if (!isEditing(cid, y)) return;
  const v = editVal.value.trim();
  editing.value = null;  // закрываем сразу — чтобы blur после Enter не сработал повторно
  if (v === editOrig.value.trim()) return;        // не изменилось — ничего не сохраняем
  if (v === "") { await saveCell(cid, y, null); return; }
  const iso = parseMasked(v);
  if (!iso) { if (explicit) toast.error("Неверная дата. Формат: дд.мм.гггг"); return; }
  await saveCell(cid, y, iso);
}

async function saveCell(cid: string, y: number, value: string | null) {
  saving.value = true;
  try {
    const row = await ifrsReportHistoryApi.upsert(cid, y, value);
    const co = { ...(histMap.value[cid] || {}) };
    co[y] = { published_on: row.published_on, updated_by_name: row.updated_by_name, updated_at: row.updated_at };
    histMap.value = { ...histMap.value, [cid]: co };
    lastChange.value = { by_name: row.updated_by_name, at: row.updated_at };
    toast.success(value ? "Дата сохранена" : "Дата очищена");
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    toast.error("Не удалось сохранить: " + (err?.response?.data?.detail || err?.message || "ошибка"));
  } finally {
    saving.value = false;
  }
}

const filledCount = computed(() => {
  let n = 0;
  for (const cid of Object.keys(histMap.value)) {
    for (const y of years.value) if (histMap.value[cid]?.[y]?.published_on) n++;
  }
  return n;
});
</script>

<template>
  <div class="ih">
    <div class="ih-head">
      <div>
        <div class="ih-title">История отчётности МСФО</div>
        <div class="ih-sub">Даты публикации МСФО-отчётности по компаниям (с 2022)<template v-if="canEdit"> · нажмите на ячейку и вводите цифры — точки проставятся сами (Enter — сохранить)</template></div>
      </div>
      <button v-if="canEdit" class="ih-addyear" type="button" title="Добавить следующий год" @click="addYear">+ год</button>
    </div>

    <div v-if="loading" class="ih-state">Загрузка…</div>

    <div v-else class="ih-tbl-wrap">
      <table class="ih-tbl">
        <thead>
          <tr>
            <th class="ih-th-co">Компания</th>
            <th v-for="y in years" :key="y" class="ih-th-y">{{ y }}</th>
            <th class="ih-th-delay" title="Дни от 31.12 года отчёта до даты публикации (по последнему заполненному году)">Лаг<span class="ih-th-mon">от 31.12, дн</span></th>
            <th class="ih-th-status" title="Относительно дедлайна 15.06 следующего года">Статус</th>
            <th class="ih-th-impr" title="Улучшение лага к предыдущему заполненному году (раньше = быстрее)">Δ к пред.<span class="ih-th-mon">году, дн</span></th>
          </tr>
        </thead>
        <tbody>
          <template v-for="g in grouped" :key="g.code">
            <tr class="ih-sec">
              <td :colspan="years.length + 4">
                <span class="ih-sec-dot" :style="{ background: g.color }"></span>{{ g.name }}
                <span class="ih-sec-cnt">({{ g.companies.length }})</span>
              </td>
            </tr>
            <tr v-for="c in g.companies" :key="c.id" class="ih-row">
              <td class="ih-co">{{ c.name_ru }}</td>
              <td
                v-for="y in years"
                :key="y"
                class="ih-cell"
                :class="{ filled: !!cellDate(c.id, y), editable: canEdit, on: isEditing(c.id, y) }"
              >
                <input
                  v-if="isEditing(c.id, y)"
                  :ref="onDateMounted"
                  v-model="editVal"
                  type="text"
                  inputmode="numeric"
                  class="ih-date"
                  placeholder="дд.мм.гггг"
                  maxlength="10"
                  @input="onMaskInput"
                  @keydown.enter.prevent="commitEdit(c.id, y, true)"
                  @keydown.esc.prevent="closeEdit"
                  @blur="commitEdit(c.id, y)"
                />
                <button
                  v-else
                  type="button"
                  class="ih-cellbtn"
                  :disabled="!canEdit"
                  :title="cellTip(c.id, y)"
                  @click="startEdit(c.id, y)"
                >{{ cellDate(c.id, y) ? fmtDate(cellDate(c.id, y)) : '—' }}</button>
              </td>
              <td class="ih-delay" :class="{ od: delayMap[c.id]?.status === 'late' }" :title="delayTip(c.id)">
                <template v-if="delayMap[c.id]?.lag != null">{{ delayMap[c.id]?.lag }} дн</template>
                <span v-else class="ih-muted">—</span>
              </td>
              <td class="ih-status">
                <span v-if="delayMap[c.id]?.status === 'late'" class="ih-badge ih-badge-od">с опозданием</span>
                <span v-else-if="delayMap[c.id]?.status === 'ontime'" class="ih-badge ih-badge-ok">в срок</span>
                <span v-else class="ih-muted">—</span>
              </td>
              <td class="ih-impr" :class="{ up: (delayMap[c.id]?.improve ?? 0) > 0, down: (delayMap[c.id]?.improve ?? 0) < 0 }" :title="delayTip(c.id)">
                <template v-if="delayMap[c.id]?.improve != null">{{ (delayMap[c.id]!.improve! > 0 ? '−' : delayMap[c.id]!.improve! < 0 ? '+' : '') }}{{ Math.abs(delayMap[c.id]!.improve!) }} дн</template>
                <span v-else class="ih-muted">—</span>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <div class="ih-foot">
      <span class="ih-foot-l">Заполнено дат: <b>{{ filledCount }}</b></span>
      <span v-if="lastChange.by_name || lastChange.at" class="ih-foot-r">
        Последнее изменение: <b>{{ lastChange.by_name || '—' }}</b><template v-if="lastChange.at"> · {{ fmtDT(lastChange.at) }}</template>
      </span>
      <span v-else class="ih-foot-r ih-foot-empty">Изменений пока не было</span>
    </div>
  </div>
</template>

<style scoped>
.ih {
  background: var(--card-bg, rgba(255, 255, 255, .82));
  border: 1px solid var(--card-border, rgba(0, 0, 0, .05));
  border-radius: 14px; padding: 18px 20px;
}
.ih-head { margin-bottom: 14px; display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.ih-addyear {
  flex-shrink: 0; padding: 6px 13px; border-radius: 8px; font-size: 12px; font-weight: 500;
  font-family: inherit; cursor: pointer;
  background: rgba(127, 119, 221, .08); border: 1px solid rgba(127, 119, 221, .25);
  color: var(--p-deep, #5B53B8); transition: all .15s;
}
.ih-addyear:hover { background: #7F77DD; color: #fff; border-color: #7F77DD; }
.ih-th-delay, .ih-th-status, .ih-th-impr { text-align: center; min-width: 92px; }
.ih-th-mon { display: block; font-size: 8.5px; font-weight: 500; text-transform: none; letter-spacing: 0; color: var(--t3, #b5b4b0); }
.ih-delay { text-align: center; font-feature-settings: "tnum"; font-weight: 600; color: var(--t3, #9aa0b0); }
.ih-delay.od { color: #E24B4A; background: rgba(226, 75, 74, .06); }
.ih-status { text-align: center; }
.ih-badge { display: inline-block; font-size: 10px; font-weight: 600; padding: 2px 9px; border-radius: 999px; white-space: nowrap; }
.ih-badge-od { background: rgba(226, 75, 74, .12); color: #933632; }
.ih-badge-ok { background: rgba(29, 158, 117, .14); color: #0F6E56; }
.ih-impr { text-align: center; font-feature-settings: "tnum"; font-weight: 600; color: var(--t3, #9aa0b0); }
.ih-impr.up { color: #0F6E56; }
.ih-impr.down { color: #E24B4A; }
.ih-muted { color: var(--t3, #b5b4b0); }
.ih-title { font-size: 14px; font-weight: 600; color: var(--t1, #1E2A4A); letter-spacing: -.01em; }
.ih-sub { font-size: 11.5px; color: var(--t3, var(--t-muted)); margin-top: 3px; }
.ih-state { padding: 30px; text-align: center; color: var(--t3, var(--t-muted)); font-size: 13px; }

.ih-tbl-wrap { overflow-x: auto; border: 1px solid var(--border1, rgba(0, 0, 0, .06)); border-radius: 12px; }
.ih-tbl { width: 100%; border-collapse: collapse; font-size: 12px; font-variant-numeric: tabular-nums; }
.ih-tbl thead th {
  position: sticky; top: 0; z-index: 1;
  padding: 9px 12px; font-size: 10px; font-weight: 600; letter-spacing: .05em;
  text-transform: uppercase; color: var(--t3, var(--t-muted));
  background: var(--bg2, #FAFBFC); border-bottom: 1.5px solid rgba(0, 0, 0, .08);
  white-space: nowrap;
}
.ih-th-co { text-align: left; min-width: 200px; }
.ih-th-y { text-align: center; min-width: 96px; }

.ih-sec td {
  padding: 7px 12px; font-size: 10.5px; font-weight: 600; text-transform: uppercase;
  letter-spacing: .04em; color: var(--t2, #5F5E5A);
  background: rgba(0, 0, 0, .025); border-bottom: 1px solid rgba(0, 0, 0, .05);
}
.ih-sec-dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 7px; vertical-align: middle; }
.ih-sec-cnt { color: var(--t3, var(--t-muted)); font-weight: 500; }

.ih-row td { border-bottom: 1px solid rgba(0, 0, 0, .035); }
.ih-row:hover { background: rgba(127, 119, 221, .03); }
.ih-co { padding: 8px 12px; color: var(--t1, #1E2A4A); font-weight: 500; white-space: nowrap; }
.ih-cell { text-align: center; padding: 4px; }
.ih-cell.filled { background: rgba(29, 158, 117, .05); }

.ih-cellbtn {
  width: 100%; min-height: 28px; padding: 4px 8px;
  background: transparent; border: 1px solid transparent; border-radius: 6px;
  font-family: inherit; font-size: 12px; font-feature-settings: "tnum";
  color: var(--t1, #1E2A4A); cursor: pointer; transition: all .12s;
}
.ih-cell:not(.filled) .ih-cellbtn { color: var(--t3, #b5b4b0); }
.ih-cell.editable .ih-cellbtn:hover { background: rgba(127, 119, 221, .1); border-color: rgba(127, 119, 221, .3); color: var(--p-deep, #5B53B8); }
.ih-cellbtn:disabled { cursor: default; }
.ih-date {
  width: 100%; padding: 4px 6px; border: 1px solid #7F77DD; border-radius: 6px;
  font-family: inherit; font-size: 12px; outline: none; box-sizing: border-box;
  box-shadow: 0 0 0 2px rgba(127, 119, 221, .15);
}

.ih-foot {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; flex-wrap: wrap; margin-top: 12px;
  font-size: 11.5px; color: var(--t3, var(--t-muted));
}
.ih-foot b { color: var(--t1, #1E2A4A); font-weight: 600; }
.ih-foot-empty { font-style: italic; }
</style>
