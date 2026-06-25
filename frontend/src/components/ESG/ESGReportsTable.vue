<script setup lang="ts">
/**
 * ESGReportsTable — годовая таблица ESG-отчётов компании (с 2021).
 * Каждая строка = год: описание/стандарт отчёта + inline-ссылка на сам отчёт.
 * Inline-правка (клик → input, Enter/blur — сохранить, Esc — отмена), тосты,
 * внизу — подпись «кто и когда менял последним». Двунаправленно через /esg API.
 */
import { computed, ref, watch } from "vue";
import { isModerationQueued } from "@/api/client";
import { esgApi, type ESGReportBrief } from "@/api/esg";
import { useToast } from "@/composables/useToast";

const props = defineProps<{
  companyId: string;
  canEdit?: boolean;
}>();

const toast = useToast();
const START_YEAR = 2021;

const items = ref<ESGReportBrief[]>([]);
const loading = ref(false);
const lastBy = ref<string | null>(null);
const lastAt = ref<string | null>(null);
const lastYear = ref<number | null>(null);

const byYear = computed<Record<number, ESGReportBrief>>(() => {
  const m: Record<number, ESGReportBrief> = {};
  for (const it of items.value) m[it.year] = it;
  return m;
});
const years = computed<number[]>(() => {
  const cur = new Date().getFullYear();
  const ys = items.value.map((i) => i.year);
  const maxY = Math.max(cur, START_YEAR, ...ys);
  const minY = Math.min(START_YEAR, ...ys);
  const out: number[] = [];
  for (let y = maxY; y >= minY; y--) out.push(y);
  return out;
});

async function load() {
  if (!props.companyId) { items.value = []; return; }
  loading.value = true;
  try {
    const data = await esgApi.getCompanyReports(props.companyId);
    items.value = data.items || [];
    lastBy.value = data.last_changed_by_name;
    lastAt.value = data.last_changed_at;
    lastYear.value = data.last_changed_year;
  } catch {
    items.value = [];
  } finally {
    loading.value = false;
  }
}
watch(() => props.companyId, load, { immediate: true });

// ── inline-редактирование одной ячейки за раз ──────────────────────
type Field = "status" | "url";
const editing = ref<{ year: number; field: Field } | null>(null);
const draft = ref("");
const saving = ref(false);

// Функция-ref: фокусирует ту единственную ячейку-input, что сейчас открыта
// (string-ref внутри v-for даёт массив — ненадёжно, поэтому callback).
function focusEl(el: unknown) {
  const inp = el as HTMLInputElement | null;
  if (inp) { inp.focus(); inp.select(); }
}

function isEditing(year: number, field: Field): boolean {
  return !!editing.value && editing.value.year === year && editing.value.field === field;
}
function startEdit(year: number, field: Field) {
  if (!props.canEdit || saving.value) return;
  const rec = byYear.value[year];
  draft.value = (field === "status" ? rec?.status : rec?.report_url) || "";
  editing.value = { year, field };
}
function cancelEdit() { editing.value = null; draft.value = ""; }

async function commitEdit() {
  const e = editing.value;
  if (!e) return;
  const rec = byYear.value[e.year];
  const prev = (e.field === "status" ? rec?.status : rec?.report_url) || "";
  const next = draft.value.trim();
  editing.value = null;
  if (next === prev.trim()) return;     // без изменений — тихо выходим
  saving.value = true;
  try {
    const payload = {
      company_id: props.companyId,
      year: e.year,
      ...(e.field === "status" ? { status: next } : { report_url: next }),
    };
    const res = await esgApi.upsertReport(payload);
    if (isModerationQueued(res)) {
      toast.info("Отправлено на согласование");
    } else {
      // обновляем локально и подпись «последнее изменение»
      const i = items.value.findIndex((x) => x.year === e.year);
      if (i >= 0) items.value[i] = res;
      else items.value.push(res);
      lastBy.value = res.changed_by_name;
      lastAt.value = res.updated_at;
      lastYear.value = res.year;
      toast.success("Сохранено");
    }
  } catch (err: unknown) {
    const x = err as { response?: { data?: { detail?: string } }; message?: string };
    toast.error("Не сохранено: " + (x?.response?.data?.detail || x?.message || "ошибка"));
  } finally {
    saving.value = false;
  }
}

function fmtDate(iso: string | null): string {
  if (!iso) return "";
  try { return new Date(iso).toLocaleDateString("ru", { day: "2-digit", month: "short", year: "numeric" }); }
  catch { return iso; }
}
function shortUrl(url: string): string {
  try { const u = new URL(url); return (u.hostname || url).replace(/^www\./, ""); }
  catch { return url.length > 28 ? url.slice(0, 27) + "…" : url; }
}
</script>

<template>
  <div class="rt">
    <div class="rt-head">
      <span class="rt-title">ESG-отчётность по годам</span>
      <span class="rt-src">Годовые отчёты устойчивого развития · ссылки и стандарты</span>
    </div>

    <div v-if="loading" class="rt-empty">Загрузка отчётов…</div>
    <table v-else class="rt-tbl">
      <thead>
        <tr>
          <th class="rt-y">Год</th>
          <th class="rt-st">ESG-отчёт / стандарт</th>
          <th class="rt-ln">Ссылка на отчёт</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(y, i) in years" :key="y" class="rt-row" :style="{ '--d': (i * 35) + 'ms' }">
          <td class="rt-y"><span class="rt-y-b">{{ y }}</span></td>

          <!-- статус / описание -->
          <td class="rt-st">
            <input v-if="isEditing(y, 'status')" :ref="focusEl" v-model="draft" type="text"
                   class="rt-inp" placeholder="например: GRI/SASB · IFRS S2 · + assurance"
                   @keydown.enter.prevent="commitEdit" @keydown.esc.stop.prevent="cancelEdit" @blur="commitEdit" />
            <button v-else type="button" class="rt-cell" :class="{ ed: canEdit, empty: !byYear[y]?.status }"
                    :disabled="!canEdit" @click="startEdit(y, 'status')">
              <span v-if="byYear[y]?.status">{{ byYear[y]?.status }}</span>
              <span v-else class="rt-ph">{{ canEdit ? '— добавить описание' : '—' }}</span>
            </button>
          </td>

          <!-- ссылка -->
          <td class="rt-ln">
            <input v-if="isEditing(y, 'url')" :ref="focusEl" v-model="draft" type="url"
                   class="rt-inp" placeholder="https://…"
                   @keydown.enter.prevent="commitEdit" @keydown.esc.stop.prevent="cancelEdit" @blur="commitEdit" />
            <div v-else class="rt-lnk-wrap">
              <a v-if="byYear[y]?.report_url" class="rt-lnk" :href="byYear[y]?.report_url || undefined"
                 target="_blank" rel="noopener" :title="byYear[y]?.report_url || ''">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                {{ shortUrl(byYear[y]?.report_url || '') }}
              </a>
              <button v-if="canEdit" type="button" class="rt-lnk-edit"
                      :title="byYear[y]?.report_url ? 'Изменить ссылку' : 'Добавить ссылку'"
                      @click="startEdit(y, 'url')">
                {{ byYear[y]?.report_url ? 'изменить' : '+ ссылка' }}
              </button>
              <span v-else-if="!byYear[y]?.report_url" class="rt-ph">—</span>
            </div>
          </td>
        </tr>
      </tbody>
    </table>

    <div v-if="lastBy || lastAt" class="rt-foot">
      Последнее изменение:
      <b>{{ lastBy || '—' }}</b>
      <template v-if="lastAt"> · {{ fmtDate(lastAt) }}</template>
      <template v-if="lastYear"> · за {{ lastYear }} г.</template>
    </div>
  </div>
</template>

<style scoped>
.rt { margin-top: 20px; padding-top: 18px; border-top: 1px solid var(--border, #ECEAF5); }
.rt-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.rt-title { font-size: 13px; font-weight: 600; color: var(--t1, #1E2A4A); }
.rt-src { font-size: 10.5px; color: var(--t3, #94A3B8); }
.rt-empty { font-size: 11.5px; color: var(--t3, #94A3B8); padding: 8px 0; }

.rt-tbl { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 12px; }
.rt-tbl thead th { font-size: 9.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: var(--t3, #94A3B8); text-align: left; padding: 0 10px 7px; border-bottom: 1px solid var(--border, #ECEAF5); }
.rt-tbl th.rt-y, .rt-tbl td.rt-y { width: 58px; }
.rt-tbl th.rt-st { width: 46%; }
.rt-row { animation: rtIn .34s var(--ease-standard, ease) var(--d, 0ms) both; }
@keyframes rtIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }
.rt-tbl td { padding: 4px 10px; border-bottom: 1px solid #F4F3FA; vertical-align: middle; }
.rt-row:hover td { background: color-mix(in srgb, #7C6FF7 4%, transparent); }
.rt-y-b { font-size: 12.5px; font-weight: 700; color: var(--p-deep, #534AB7); font-feature-settings: 'tnum'; }

.rt-cell { width: 100%; text-align: left; background: transparent; border: 1px solid transparent; border-radius: 7px; padding: 5px 8px; font-size: 12px; font-family: inherit; color: var(--t1, #1E2A4A); cursor: default; transition: background .14s, border-color .14s; }
.rt-cell.ed { cursor: text; }
.rt-cell.ed:hover { background: #fff; border-color: var(--border, #ECEAF5); }
.rt-cell.empty { color: var(--t3, #94A3B8); }
.rt-ph { color: #B7BBCB; font-style: italic; }

.rt-inp { width: 100%; box-sizing: border-box; font-size: 12px; font-family: inherit; color: var(--t1, #1E2A4A); padding: 5px 8px; border: 1px solid var(--brand, #6C5CE7); border-radius: 7px; outline: none; background: #fff; box-shadow: 0 0 0 3px color-mix(in srgb, var(--brand, #6C5CE7) 12%, transparent); }

.rt-lnk-wrap { display: inline-flex; align-items: center; gap: 10px; }
.rt-lnk { display: inline-flex; align-items: center; gap: 4px; font-size: 11.5px; font-weight: 600; color: var(--brand, #6C5CE7); text-decoration: none; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rt-lnk:hover { text-decoration: underline; }
.rt-lnk svg { flex-shrink: 0; }
.rt-lnk-edit { font-size: 10.5px; font-weight: 600; color: var(--t3, #94A3B8); background: transparent; border: 1px solid var(--border, #ECEAF5); border-radius: 6px; padding: 2px 8px; cursor: pointer; transition: all .14s ease; }
.rt-lnk-edit:hover { color: var(--brand, #6C5CE7); border-color: color-mix(in srgb, var(--brand, #6C5CE7) 40%, #fff); background: color-mix(in srgb, var(--brand, #6C5CE7) 6%, #fff); }

.rt-foot { margin-top: 12px; font-size: 10.5px; color: var(--t3, #94A3B8); }
.rt-foot b { color: var(--t2, #475569); font-weight: 600; }

@media (min-width: 2200px) {
  .rt-title { font-size: 16px; }
  .rt-tbl { font-size: 15px; }
  .rt-y-b { font-size: 15px; }
  .rt-cell, .rt-inp { font-size: 15px; }
  .rt-lnk { font-size: 14px; max-width: 320px; }
  .rt-foot { font-size: 13px; }
}
</style>
