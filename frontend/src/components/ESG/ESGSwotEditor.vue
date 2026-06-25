<script setup lang="ts">
/**
 * ESGSwotEditor — «Выводы» ESG единой редактируемой таблицей:
 *   строка «Весь портфель» (scope=portfolio) + компании, СГРУППИРОВАННЫЕ ПО СЕКТОРАМ
 *   (scope=company). Одинаковые ячейки: сильные стороны / проблемные зоны.
 * Inline-правка: клик → textarea → ✓/Enter сохранить, ✕/Esc отмена; «+ добавить».
 * Сохранение через PUT /esg/swot (upsert). Премиум: top-accent, анимации строк.
 */
import { computed, nextTick, onMounted, ref, watch } from "vue";
import ModalShell from "@/components/ModalShell.vue";
import { esgApi, type ESGSwotResponse, type ESGSwotItemBrief, type ESGKpiBrief, type ESGKpiManagerBrief } from "@/api/esg";
import { useToast } from "@/composables/useToast";

interface CoBrief {
  company_id: string; company_name: string;
  sector_code?: string | null; sector_name?: string | null; sector_color?: string | null;
}
type Scope = "portfolio" | "company";
type Kind = "strength" | "weakness";

const props = defineProps<{
  swot: ESGSwotResponse | null;
  companies: CoBrief[];
  canEdit: boolean;
  year?: number | null;
}>();
const emit = defineEmits<{ (e: "saved"): void }>();

const toast = useToast();

// ── ESG-релевантные KPI по компаниям (read-only, подтянуты из модуля KPI) ──
const kpiMap = ref<Map<string, ESGKpiBrief[]>>(new Map());
async function loadKpis() {
  try {
    const data = await esgApi.getEsgKpis(props.year ?? undefined);
    const m = new Map<string, ESGKpiBrief[]>();
    for (const it of (data.items || [])) m.set(it.company_id, it.kpis || []);
    kpiMap.value = m;
  } catch { kpiMap.value = new Map(); }
}
onMounted(loadKpis);
watch(() => props.year, loadKpis);
function kpisFor(cid: string): ESGKpiBrief[] { return kpiMap.value.get(cid) || []; }
function kpiColor(pct: number | null): string {
  if (pct == null) return "#94A3B8";
  if (pct >= 100) return "#1D9E75";
  if (pct >= 80) return "#D97706";
  return "#E24B4A";
}
function fmtKpiNum(n: number | null): string {
  return n == null ? "—" : n.toLocaleString("ru-RU", { maximumFractionDigits: 1 });
}

// ── ручное добавление ESG-KPI → пишется в модуль KPI (sync с /kpi) ──
const addKpi = ref<{ cid: string; name: string } | null>(null);
const kName = ref(""); const kUnit = ref(""); const kDir = ref<"up" | "down">("up");
const kPlan = ref(""); const kFact = ref(""); const kSaving = ref(false);
const kMgrs = ref<ESGKpiManagerBrief[]>([]);   // существующие должности компании
const kMgr = ref("");                          // выбранная должность (manager_id); "" = ESG-менеджер
async function openAddKpi(cid: string, companyName: string) {
  if (!props.canEdit) return;
  addKpi.value = { cid, name: companyName };
  kName.value = ""; kUnit.value = ""; kDir.value = "up"; kPlan.value = ""; kFact.value = ""; kMgr.value = "";
  kMgrs.value = [];
  try { kMgrs.value = await esgApi.getEsgKpiManagers(cid, props.year ?? undefined); } catch { kMgrs.value = []; }
}
function closeKpi() { addKpi.value = null; }
async function submitKpi() {
  if (!addKpi.value || !kName.value.trim() || kSaving.value) return;
  kSaving.value = true;
  try {
    await esgApi.addEsgKpi({
      company_id: addKpi.value.cid,
      year: props.year ?? new Date().getFullYear(),
      name: kName.value.trim(),
      unit: kUnit.value.trim() || null,
      direction: kDir.value,
      plan: kPlan.value === "" ? null : Number(kPlan.value),
      fact: kFact.value === "" ? null : Number(kFact.value),
      manager_id: kMgr.value || null,
    });
    toast.success("KPI добавлен · синхронизирован с /kpi");
    closeKpi();
    await loadKpis();
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    toast.error("Не добавлено: " + (err?.response?.data?.detail || err?.message || "ошибка"));
  } finally { kSaving.value = false; }
}

// ── деривация из props ────────────────────────────────────────────
const portStrengths = computed(() => props.swot?.portfolio_strengths ?? []);
const portWeaknesses = computed(() => props.swot?.portfolio_weaknesses ?? []);

const byCompany = computed(() => {
  const m = new Map<string, { strength: ESGSwotItemBrief[]; weakness: ESGSwotItemBrief[] }>();
  for (const it of (props.swot?.company_items ?? [])) {
    if (!it.company_id) continue;
    let g = m.get(it.company_id);
    if (!g) { g = { strength: [], weakness: [] }; m.set(it.company_id, g); }
    (it.kind === "strength" ? g.strength : g.weakness).push(it);
  }
  return m;
});

// группировка компаний по секторам (порядок — как пришёл из heatmap)
const sectorGroups = computed(() => {
  const out: { key: string; name: string; color: string; companies: CoBrief[] }[] = [];
  const idx = new Map<string, number>();
  for (const c of props.companies) {
    const key = c.sector_code || "—";
    let i = idx.get(key);
    if (i === undefined) {
      i = out.length; idx.set(key, i);
      out.push({ key, name: c.sector_name || "Прочее", color: c.sector_color || "#94A3B8", companies: [] });
    }
    out[i].companies.push(c);
  }
  return out;
});

// плоский список строк таблицы: портфель → [сектор-заголовок → компании]…
interface SweRow { type: "portfolio" | "sector" | "company"; label: string; scope?: Scope; cid?: string; color?: string; count?: number }
const tableRows = computed<SweRow[]>(() => {
  const rows: SweRow[] = [
    { type: "portfolio", label: "Весь портфель", scope: "portfolio", cid: "", color: "#7C6FF7" },
  ];
  for (const g of sectorGroups.value) {
    rows.push({ type: "sector", label: g.name, color: g.color, count: g.companies.length });
    for (const c of g.companies) {
      rows.push({ type: "company", label: c.company_name, scope: "company", cid: c.company_id, color: c.sector_color || g.color });
    }
  }
  return rows;
});

function itemsFor(scope: Scope, cid: string, kind: Kind): ESGSwotItemBrief[] {
  if (scope === "portfolio") return kind === "strength" ? portStrengths.value : portWeaknesses.value;
  const g = byCompany.value.get(cid);
  return g ? g[kind] : [];
}

// ── inline-edit ───────────────────────────────────────────────────
const editKey = ref<string | null>(null);
const draft = ref("");
const saving = ref(false);
const taRef = ref<HTMLTextAreaElement | null>(null);

function keyOf(it: ESGSwotItemBrief): string { return "id:" + (it.id || ""); }
function newKey(scope: string, kind: string, cid: string): string { return `new:${scope}:${kind}:${cid}`; }

async function startEdit(it: ESGSwotItemBrief) {
  if (!props.canEdit) return;
  editKey.value = keyOf(it);
  draft.value = it.body;
  await nextTick(); taRef.value?.focus();
}
async function startAdd(scope: Scope, kind: Kind, cid = "") {
  if (!props.canEdit) return;
  editKey.value = newKey(scope, kind, cid);
  draft.value = "";
  await nextTick(); taRef.value?.focus();
}
function cancelEdit() { editKey.value = null; draft.value = ""; }

async function commit(scope: Scope, kind: Kind, cid: string, existing: ESGSwotItemBrief | null, listLen: number) {
  const body = draft.value.trim();
  if (!body) { cancelEdit(); return; }
  if (saving.value) return;
  saving.value = true;
  try {
    const r = await esgApi.upsertSwot({
      id: existing?.id ?? null, kind, scope,
      company_id: scope === "company" ? cid : null,
      body, order_idx: existing?.order_idx ?? listLen,
    });
    if ((r as { queued?: boolean }).queued) toast.info("Отправлено на согласование");
    else { toast.success("Сохранено"); emit("saved"); }
    cancelEdit();
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    toast.error("Не сохранено: " + (err?.response?.data?.detail || err?.message || "ошибка"));
  } finally { saving.value = false; }
}

const KIND_AC: Record<Kind, string> = { strength: "#1D9E75", weakness: "#EF9F27" };
const KINDS: Kind[] = ["strength", "weakness"];
</script>

<template>
  <div class="swe">
    <div class="swe-head">
      <h2 class="swe-title">Выводы</h2>
      <span class="swe-sub">ESG-аналитика: портфель и по компаниям (по секторам)</span>
    </div>

    <div class="swe-table">
      <!-- шапка -->
      <div class="swe-tr swe-thead">
        <div class="swe-th swe-th-co">Объект</div>
        <div class="swe-th"><span class="swe-dot" style="background:#1D9E75"></span>Сильные стороны</div>
        <div class="swe-th"><span class="swe-dot" style="background:#EF9F27"></span>Проблемные зоны</div>
        <div class="swe-th"><span class="swe-dot" style="background:#7C6FF7"></span>ESG-KPI{{ year ? ' · ' + year : '' }}</div>
      </div>

      <template v-for="(row, ri) in tableRows" :key="row.type === 'sector' ? 'sec:'+row.label : (row.scope+':'+row.cid)">
        <!-- секторный разделитель -->
        <div v-if="row.type === 'sector'" class="swe-sec-row" :style="{ '--sc': row.color }">
          <span class="swe-sec-dot" :style="{ background: row.color }"></span>{{ row.label }}
          <span class="swe-sec-cnt">{{ row.count }}</span>
        </div>

        <!-- строка портфеля / компании -->
        <div v-else class="swe-tr swe-trow" :class="{ 'swe-portfolio': row.type === 'portfolio' }"
             :style="{ '--d': Math.min(ri * 18, 360) + 'ms' }">
          <div class="swe-td swe-td-co">
            <span class="swe-co-dot" :style="{ background: row.color }"></span>{{ row.label }}
          </div>

          <div v-for="kind in KINDS" :key="kind" class="swe-td">
            <div class="swe-cell-list">
              <div v-for="(it, i) in itemsFor(row.scope!, row.cid!, kind)" :key="it.id || (kind+i)"
                   class="swe-citem" :class="{ 'swe-citem-num': row.type === 'portfolio' }" :style="{ '--ac': KIND_AC[kind] }">
                <textarea v-if="editKey === keyOf(it)" ref="taRef" v-model="draft" class="swe-ta sm" rows="2"
                          @keydown.enter.exact.prevent="commit(row.scope!, kind, row.cid!, it, itemsFor(row.scope!, row.cid!, kind).length)"
                          @keydown.esc.prevent="cancelEdit"></textarea>
                <template v-else>
                  <span v-if="row.type === 'portfolio'" class="swe-cnum" :style="{ background: KIND_AC[kind] + '22', color: KIND_AC[kind] }">{{ i + 1 }}</span>
                  <p class="swe-cbody" :class="{ ed: canEdit }" @click="startEdit(it)">{{ it.body }}</p>
                </template>
                <div v-if="editKey === keyOf(it)" class="swe-confirm sm">
                  <button class="swe-ok" :disabled="saving" @click="commit(row.scope!, kind, row.cid!, it, itemsFor(row.scope!, row.cid!, kind).length)">✓</button>
                  <button class="swe-no" @click="cancelEdit">✕</button>
                </div>
              </div>

              <div v-if="editKey === newKey(row.scope!, kind, row.cid!)" class="swe-citem swe-item-new" :style="{ '--ac': KIND_AC[kind] }">
                <textarea ref="taRef" v-model="draft" class="swe-ta sm" rows="2" placeholder="Текст…"
                          @keydown.enter.exact.prevent="commit(row.scope!, kind, row.cid!, null, itemsFor(row.scope!, row.cid!, kind).length)"
                          @keydown.esc.prevent="cancelEdit"></textarea>
                <div class="swe-confirm sm">
                  <button class="swe-ok" :disabled="saving" @click="commit(row.scope!, kind, row.cid!, null, itemsFor(row.scope!, row.cid!, kind).length)">✓</button>
                  <button class="swe-no" @click="cancelEdit">✕</button>
                </div>
              </div>
              <button v-else-if="canEdit" class="swe-add sm" @click="startAdd(row.scope!, kind, row.cid!)">+ добавить</button>
              <span v-if="!itemsFor(row.scope!, row.cid!, kind).length && !canEdit" class="swe-empty">—</span>
            </div>
          </div>

          <!-- ESG-KPI: подтянуто из модуля KPI по контексту + ручное добавление (sync с /kpi) -->
          <div class="swe-td swe-td-kpi">
            <template v-if="row.scope === 'company'">
              <div v-if="kpisFor(row.cid!).length" class="swe-kpi-list">
                <div v-for="(k, ki) in kpisFor(row.cid!)" :key="ki" class="swe-kpi"
                     :title="(k.manager ? k.manager + ' · ' : '') + k.name">
                  <span class="swe-kpi-name">{{ k.name }}</span>
                  <span class="swe-kpi-val">
                    <b :style="{ color: kpiColor(k.pct) }">{{ fmtKpiNum(k.fact) }}</b>
                    <span class="swe-kpi-plan">/ {{ fmtKpiNum(k.plan) }}<template v-if="k.unit"> {{ k.unit }}</template></span>
                    <span v-if="k.pct != null" class="swe-kpi-pct"
                          :style="{ color: kpiColor(k.pct), background: kpiColor(k.pct) + '18' }">{{ Math.round(k.pct) }}%</span>
                  </span>
                </div>
              </div>
              <span v-else-if="!canEdit" class="swe-empty">—</span>
              <button v-if="canEdit" class="swe-kpi-add" @click="openAddKpi(row.cid!, row.label)">+ KPI</button>
            </template>
            <span v-else class="swe-empty">—</span>
          </div>
        </div>
      </template>
    </div>

    <!-- Модалка ручного добавления ESG-KPI (пишет в модуль KPI) -->
    <ModalShell :open="!!addKpi" size="sm" @close="closeKpi">
      <template #header><div class="swe-km-title">Добавить ESG-KPI · {{ addKpi?.name }}</div></template>
      <div v-if="addKpi" class="swe-km">
        <label class="swe-km-f"><span>Название KPI *</span>
          <input v-model="kName" type="text" placeholder="напр.: Снижение выбросов CO₂, % к 2022" @keydown.enter="submitKpi" />
        </label>
        <label class="swe-km-f"><span>Должность (ответственный)</span>
          <select v-model="kMgr">
            <option value="">ESG / Устойчивое развитие (по умолчанию)</option>
            <option v-for="m in kMgrs" :key="m.id" :value="m.id">{{ m.short_title || m.title }}</option>
          </select>
        </label>
        <div class="swe-km-row">
          <label class="swe-km-f"><span>Ед. изм.</span><input v-model="kUnit" type="text" placeholder="%, т, чел…" /></label>
          <label class="swe-km-f"><span>Направление</span>
            <select v-model="kDir"><option value="up">больше — лучше</option><option value="down">меньше — лучше</option></select>
          </label>
        </div>
        <div class="swe-km-row">
          <label class="swe-km-f"><span>План{{ year ? ' · ' + year : '' }}</span><input v-model="kPlan" type="number" step="any" placeholder="—" /></label>
          <label class="swe-km-f"><span>Факт{{ year ? ' · ' + year : '' }}</span><input v-model="kFact" type="number" step="any" placeholder="—" /></label>
        </div>
        <div class="swe-km-note">Сохранится в модуле «KPI» под менеджером «ESG / Устойчивое развитие» — появится и в <b>/kpi</b>.</div>
        <div class="swe-km-actions">
          <button class="swe-km-cancel" type="button" @click="closeKpi">Отмена</button>
          <button class="swe-km-save" type="button" :disabled="kSaving || !kName.trim()" @click="submitKpi">{{ kSaving ? 'Сохранение…' : 'Добавить KPI' }}</button>
        </div>
      </div>
    </ModalShell>
  </div>
</template>

<style scoped>
.swe { margin-top: 26px; }
.swe-head { display: flex; align-items: baseline; gap: 12px; margin-bottom: 14px; }
.swe-title { font-size: 17px; font-weight: 600; color: var(--t1, #1E2A4A); margin: 0; }
.swe-sub { font-size: 11.5px; color: var(--t3, #94A3B8); }
.swe-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }

.swe-table { border: 1px solid rgba(0,0,0,.06); border-radius: 14px; overflow: auto; background: var(--bg1, #fff); }
.swe-tr { display: grid; grid-template-columns: 200px 1fr 1fr 1.15fr; }
.swe-thead { background: #F6F5FB; position: sticky; top: 0; z-index: 1; }
.swe-th { padding: 10px 14px; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: var(--p-deep, #534AB7); display: flex; align-items: center; gap: 7px; }

/* секторный разделитель */
.swe-sec-row {
  display: flex; align-items: center; gap: 8px; padding: 7px 14px;
  font-size: 10.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em;
  color: var(--p-deep, #5B53B8);
  background: linear-gradient(90deg, color-mix(in srgb, var(--sc) 10%, #fff), transparent);
  border-top: 1px solid #F1F0F7; border-bottom: 1px solid #F1F0F7;
}
.swe-sec-dot { width: 8px; height: 8px; border-radius: 2px; flex-shrink: 0; }
.swe-sec-cnt { margin-left: 4px; font-size: 10px; font-weight: 700; color: var(--t3, #94A3B8); background: #fff; border-radius: 999px; padding: 0 7px; }

.swe-trow { border-top: 1px solid #F1F0F7; transition: background .12s; animation: sweRowIn .4s var(--ease-standard, ease) var(--d, 0ms) both; }
.swe-trow:first-of-type { border-top: none; }
.swe-trow:hover { background: #FBFAFF; }
.swe-portfolio { background: color-mix(in srgb, #7C6FF7 5%, #fff); }
.swe-portfolio .swe-td-co { font-weight: 700; color: var(--p-deep, #5B53B8); }
@keyframes sweRowIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }

.swe-td { padding: 10px 14px; border-left: 1px solid #F1F0F7; }
.swe-td-co { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--t1, #1E2A4A); border-left: none; }
.swe-co-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }

.swe-cell-list { display: flex; flex-direction: column; gap: 7px; }
.swe-citem { position: relative; display: flex; align-items: flex-start; gap: 7px; padding-left: 12px; }
.swe-citem::before { content: ''; position: absolute; left: 0; top: 7px; width: 5px; height: 5px; border-radius: 50%; background: var(--ac); }
.swe-citem-num { padding-left: 0; }
.swe-citem-num::before { display: none; }
.swe-cnum { flex-shrink: 0; width: 16px; height: 16px; border-radius: 5px; display: inline-flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 700; margin-top: .5px; }
.swe-cbody { margin: 0; font-size: 11.5px; line-height: 1.5; color: var(--t2, #3a4256); flex: 1; }
.swe-cbody.ed { cursor: text; }
.swe-cbody.ed:hover { color: var(--t1, #1E2A4A); }
.swe-citem.swe-item-new { padding-left: 0; flex-direction: column; }
.swe-citem.swe-item-new::before { display: none; }
.swe-empty { color: #CBD2E0; font-size: 12px; }

.swe-ta { width: 100%; resize: vertical; min-height: 40px; padding: 7px 10px; border: 1.5px solid #7C6FF7; border-radius: 9px; font-family: inherit; font-size: 11.5px; line-height: 1.45; color: var(--t1, #1E2A4A); outline: none; }
.swe-confirm { display: inline-flex; gap: 4px; flex-shrink: 0; }
.swe-confirm.sm { margin-top: 4px; }
.swe-ok, .swe-no { width: 22px; height: 22px; border-radius: 6px; border: none; cursor: pointer; font-size: 12px; font-weight: 700; display: inline-flex; align-items: center; justify-content: center; transition: background .12s, color .12s; }
.swe-ok { background: #DCFCE7; color: #1D9E75; }
.swe-ok:hover:not(:disabled) { background: #16A34A; color: #fff; }
.swe-ok:disabled { opacity: .5; cursor: default; }
.swe-no { background: #F1F5F9; color: #94A3B8; }
.swe-no:hover { background: #E2E8F0; color: #475569; }
.swe-add { align-self: flex-start; font-size: 11px; font-weight: 600; color: var(--p-deep, #5B53B8); background: rgba(124,111,247,.08); border: 1px dashed rgba(124,111,247,.4); border-radius: 8px; padding: 4px 10px; cursor: pointer; font-family: inherit; transition: background .14s, border-color .14s; }
.swe-add:hover { background: rgba(124,111,247,.15); border-color: #7C6FF7; }

/* ESG-KPI колонка (read-only) */
.swe-kpi-list { display: flex; flex-direction: column; gap: 7px; }
.swe-kpi { display: flex; flex-direction: column; gap: 1px; }
.swe-kpi-name { font-size: 11px; line-height: 1.35; color: var(--t2, #3a4256); }
.swe-kpi-val { display: inline-flex; align-items: baseline; gap: 5px; font-size: 11px; font-feature-settings: 'tnum'; flex-wrap: wrap; }
.swe-kpi-val b { font-weight: 700; }
.swe-kpi-plan { color: var(--t3, #94A3B8); }
.swe-kpi-pct { font-size: 9.5px; font-weight: 700; border-radius: 5px; padding: 0 5px; }
.swe-kpi-add { align-self: flex-start; margin-top: 4px; font-size: 10.5px; font-weight: 600; color: var(--p-deep, #5B53B8); background: rgba(124,111,247,.08); border: 1px dashed rgba(124,111,247,.4); border-radius: 8px; padding: 3px 9px; cursor: pointer; font-family: inherit; transition: background .14s, border-color .14s; }
.swe-kpi-add:hover { background: rgba(124,111,247,.15); border-color: #7C6FF7; }

/* модалка ручного добавления ESG-KPI */
.swe-km-title { font-size: 14px; font-weight: 600; color: var(--t1, #1E2A4A); }
.swe-km { display: flex; flex-direction: column; gap: 12px; }
.swe-km-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.swe-km-f { display: flex; flex-direction: column; gap: 5px; }
.swe-km-f span { font-size: 11px; font-weight: 600; color: var(--t3, #94A3B8); text-transform: uppercase; letter-spacing: .03em; }
.swe-km-f input, .swe-km-f select { font-family: inherit; font-size: 13px; color: var(--t1, #1E2A4A); padding: 8px 11px; border: 1px solid var(--border, #ECEAF5); border-radius: 9px; outline: none; background: #fff; transition: border-color .14s, box-shadow .14s; }
.swe-km-f input:focus, .swe-km-f select:focus { border-color: var(--brand, #6C5CE7); box-shadow: 0 0 0 3px color-mix(in srgb, var(--brand, #6C5CE7) 12%, transparent); }
.swe-km-note { font-size: 11px; color: var(--t3, #94A3B8); line-height: 1.4; background: var(--surface-2, #FAFAFC); border-radius: 8px; padding: 8px 11px; }
.swe-km-note b { color: var(--p-deep, #5B53B8); }
.swe-km-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 2px; }
.swe-km-cancel { font-size: 12.5px; font-weight: 600; color: var(--t2, #475569); background: #fff; border: 1px solid var(--border, #ECEAF5); border-radius: 9px; padding: 8px 16px; cursor: pointer; font-family: inherit; }
.swe-km-cancel:hover { background: #F1F5F9; }
.swe-km-save { font-size: 12.5px; font-weight: 600; color: #fff; background: var(--brand, #6C5CE7); border: none; border-radius: 9px; padding: 8px 18px; cursor: pointer; font-family: inherit; transition: background .14s; }
.swe-km-save:hover:not(:disabled) { background: var(--p-deep, #5B53B8); }
.swe-km-save:disabled { opacity: .5; cursor: default; }

@media (max-width: 900px) {
  .swe-tr { grid-template-columns: 1fr; }
  .swe-td { border-left: none; border-top: 1px dashed #F1F0F7; }
  .swe-td-co { border-top: none; }
}
@media (min-width: 2200px) {
  .swe-title { font-size: 21px; } .swe-cbody { font-size: 14px; }
  .swe-tr { grid-template-columns: 280px 1fr 1fr 1.15fr; } .swe-th { font-size: 13px; } .swe-td-co { font-size: 15px; }
}
</style>
