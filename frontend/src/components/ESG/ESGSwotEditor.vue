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
import { useConfirm } from "@/composables/useConfirm";
import { useCompanyScope } from "@/composables/useCompanyScope";
import { useI18n } from "@/composables/useI18n";
import { getCurrentIntlLocale } from "@/locale/i18n";
import { i18nKey } from "@/locale/keys";
import { resolveCompanyDisplayName, resolveSectorDisplayName } from "@/utils/displayNames";

const { t } = useI18n();

// ── Подпись автора: инициалы + локализованная дата ──
function authorInitials(name: string): string {
  const parts = name.split(" ").filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}
function authorSub(it: ESGSwotItemBrief): string {
  return [it.created_by_title, it.created_by_org].filter(Boolean).join(" · ");
}
function authorDate(it: ESGSwotItemBrief): string {
  if (!it.created_at) return "";
  try {
    return new Date(it.created_at).toLocaleDateString(getCurrentIntlLocale(), {
      day: "numeric", month: "short", year: "numeric",
    });
  } catch { return ""; }
}



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
const { confirmDialog } = useConfirm();

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
  return n == null ? "—" : n.toLocaleString(getCurrentIntlLocale(), { maximumFractionDigits: 1 });
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
    toast.success(t('KPI добавлен · синхронизирован с /kpi'));
    closeKpi();
    await loadKpis();
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    toast.error(t('Не добавлено: {value0}', { value0: (err?.response?.data?.detail || err?.message || t("ошибка")) }));
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
      out.push({
        key,
        name: resolveSectorDisplayName(c.sector_name || c.sector_code, c.sector_code) || t("Прочее"),
        color: c.sector_color || "#94A3B8",
        companies: [],
      });
    }
    out[i].companies.push(c);
  }
  return out;
});

// плоский список строк таблицы: портфель → [сектор-заголовок → компании]…
// Область доступа: скрывает портфельные строки у компанийных пользователей.
const coScope = useCompanyScope();

interface SweRow { type: "portfolio" | "sector" | "company"; label: string; scope?: Scope; cid?: string; color?: string; count?: number }
const tableRows = computed<SweRow[]>(() => {
  // Выводы по ВСЕМУ портфелю — портфельный срез: пользователю, ограниченному
  // своими компаниями, он не показывается (решение владельца 29.07.2026).
  // Иначе компания читала бы сводные оценки по всем 22 организациям.
  const rows: SweRow[] = coScope.showPortfolioViews.value
    ? [{ type: "portfolio", label: i18nKey("Весь портфель"), scope: "portfolio", cid: "", color: "#7C6FF7" }]
    : [];
  for (const g of sectorGroups.value) {
    rows.push({ type: "sector", label: g.name, color: g.color, count: g.companies.length });
    for (const c of g.companies) {
      rows.push({
        type: "company",
        label: resolveCompanyDisplayName(c.company_name, c.company_id) || c.company_name,
        scope: "company",
        cid: c.company_id,
        color: c.sector_color || g.color,
      });
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
    await esgApi.upsertSwot({
      id: existing?.id ?? null, kind, scope,
      company_id: scope === "company" ? cid : null,
      body, order_idx: existing?.order_idx ?? listLen,
    });
    toast.success(t('Сохранено')); emit("saved");
    cancelEdit();
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    toast.error(t('Не сохранено: {value0}', { value0: (err?.response?.data?.detail || err?.message || t("ошибка")) }));
  } finally { saving.value = false; }
}

async function removeItem(it: ESGSwotItemBrief) {
  if (!props.canEdit || !it.id || saving.value) return;
  const ok = await confirmDialog({
    title: t("Удалить вывод"),
    message: t("«{text}» будет удалён. Действие необратимо.", { text: (it.body || "").slice(0, 120) }),
    confirmText: t("Удалить"),
    danger: true,
  });
  if (!ok) return;
  saving.value = true;
  try {
    await esgApi.deleteSwot(it.id);
    toast.success(t('Вывод удалён')); emit("saved");
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    toast.error(t('Не удалено: {value0}', { value0: (err?.response?.data?.detail || err?.message || t("ошибка")) }));
  } finally { saving.value = false; }
}

const KIND_AC: Record<Kind, string> = { strength: "#1D9E75", weakness: "#E24B4A" };
const KIND_TITLE: Record<Kind, string> = { strength: i18nKey("↑ Сильные стороны"), weakness: i18nKey("↓ Проблемные зоны") };
const KINDS: Kind[] = ["strength", "weakness"];
// компании для секции ESG-KPI (все, чтобы можно было добавить; при read-only — только с KPI)
const kpiCompanies = computed(() =>
  tableRows.value.filter((r) => r.type === "company" && (props.canEdit || kpisFor(r.cid!).length)),
);
</script>

<template>
  <div class="swe">
    <div class="swe-head">
      <h2 class="swe-title">{{ t('Выводы') }}</h2>
      <span class="swe-sub">{{ t('ESG-аналитика: портфель и по компаниям (по секторам)') }}</span>
    </div>

    <!-- Две панели «по типу KPI»: Сильные стороны (зелёная) · Проблемные зоны (красная) -->
    <div class="swe-grid2">
      <div v-for="kind in KINDS" :key="kind" class="swe-w">
        <div class="swe-w-t" :style="{ color: KIND_AC[kind] }">{{ t(KIND_TITLE[kind]) }}</div>
        <div class="swe-obj-list">
          <template v-for="(row, ri) in tableRows" :key="kind+':'+(row.type==='sector' ? 'sec:'+row.label : row.scope+':'+row.cid)">
            <!-- секторный разделитель -->
            <div v-if="row.type === 'sector'" class="swe-obj-sec">
              <span class="swe-obj-sec-dot" :style="{ background: row.color }"></span>{{ t(row.label) }}
              <span class="swe-obj-sec-cnt">{{ row.count }}</span>
            </div>
            <!-- объект (портфель / компания) со своими пунктами -->
            <div v-else class="swe-obj" :class="{ port: row.type === 'portfolio' }"
                 :style="{ '--d': Math.min(ri * 14, 300) + 'ms' }">
              <div class="swe-obj-h"><span class="swe-obj-dot" :style="{ background: row.color }"></span>{{ t(row.label) }}</div>
              <div class="swe-items">
                <div v-for="(it, i) in itemsFor(row.scope!, row.cid!, kind)" :key="it.id || (kind+i)"
                     class="swe-item" :class="kind === 'strength' ? 'good' : 'bad'">
                  <template v-if="editKey === keyOf(it)">
                    <textarea ref="taRef" v-model="draft" class="swe-ta" rows="2"
                              @keydown.enter.exact.prevent="commit(row.scope!, kind, row.cid!, it, itemsFor(row.scope!, row.cid!, kind).length)"
                              @keydown.esc.prevent="cancelEdit"></textarea>
                    <div class="swe-confirm">
                      <button class="swe-ok" :disabled="saving" @click="commit(row.scope!, kind, row.cid!, it, itemsFor(row.scope!, row.cid!, kind).length)">✓</button>
                      <button class="swe-no" @click="cancelEdit">✕</button>
                    </div>
                  </template>
                  <div v-else class="swe-item-main" :class="{ ed: canEdit }" @click="startEdit(it)">
                    <p class="swe-item-body">{{ it.body }}</p>
                  <div v-if="it.created_by_name" class="swe-author">
                    <span class="swe-author-ava">{{ authorInitials(it.created_by_name) }}</span>
                    <span class="swe-author-col">
                      <span class="swe-author-name">{{ it.created_by_name }}</span>
                      <span v-if="authorSub(it)" class="swe-author-sub">{{ authorSub(it) }}</span>
                    </span>
                    <span v-if="authorDate(it)" class="swe-author-date">{{ authorDate(it) }}</span>
                  </div>
                  </div>
                  <button v-if="canEdit && it.id && editKey !== keyOf(it)"
                          class="swe-del" :disabled="saving"
                          :title="t('Удалить вывод')" @click.stop="removeItem(it)">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 6h18M8 6V4h8v2m1 0-1 14H8L7 6"/></svg>
                  </button>
                </div>

                <div v-if="editKey === newKey(row.scope!, kind, row.cid!)" class="swe-item swe-item-new" :class="kind === 'strength' ? 'good' : 'bad'">
                  <textarea ref="taRef" v-model="draft" class="swe-ta" rows="2" :placeholder="t('Текст…')"
                            @keydown.enter.exact.prevent="commit(row.scope!, kind, row.cid!, null, itemsFor(row.scope!, row.cid!, kind).length)"
                            @keydown.esc.prevent="cancelEdit"></textarea>
                  <div class="swe-confirm">
                    <button class="swe-ok" :disabled="saving" @click="commit(row.scope!, kind, row.cid!, null, itemsFor(row.scope!, row.cid!, kind).length)">✓</button>
                    <button class="swe-no" @click="cancelEdit">✕</button>
                  </div>
                </div>
                <button v-else-if="canEdit" class="swe-add" @click="startAdd(row.scope!, kind, row.cid!)">{{ t('+ добавить') }}</button>
                <span v-if="!itemsFor(row.scope!, row.cid!, kind).length && !canEdit" class="swe-empty">—</span>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>

    <!-- ESG-KPI по компаниям (из модуля KPI) — отдельной лентой под панелями -->
    <div v-if="kpiCompanies.length" class="swe-w swe-kpi-sec">
      <div class="swe-w-t" style="color:#7C6FF7">{{ t('ESG-KPI по компаниям') }}{{ year ? ' · ' + year : '' }}</div>
      <div class="swe-kpi-grid">
        <div v-for="row in kpiCompanies" :key="'k:'+row.cid" class="swe-kpi-co">
          <div class="swe-kpi-co-h"><span class="swe-obj-dot" :style="{ background: row.color }"></span>{{ t(row.label) }}</div>
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
          <button v-if="canEdit" class="swe-kpi-add" @click="openAddKpi(row.cid!, row.label)">+ KPI</button>
        </div>
      </div>
    </div>

    <!-- Модалка ручного добавления ESG-KPI (пишет в модуль KPI) -->
    <ModalShell :open="!!addKpi" size="sm" @close="closeKpi">
      <template #header><div class="swe-km-title">{{ t('Добавить ESG-KPI ·') }} {{ addKpi?.name }}</div></template>
      <div v-if="addKpi" class="swe-km">
        <label class="swe-km-f"><span>{{ t('Название KPI *') }}</span>
          <input v-model="kName" type="text" :placeholder="t('напр.: Снижение выбросов CO₂, % к 2022')" @keydown.enter="submitKpi" />
        </label>
        <label class="swe-km-f"><span>{{ t('Должность (ответственный)') }}</span>
          <select v-model="kMgr">
            <option value="">{{ t('ESG / Устойчивое развитие (по умолчанию)') }}</option>
            <option v-for="m in kMgrs" :key="m.id" :value="m.id">{{ m.short_title || m.title }}</option>
          </select>
        </label>
        <div class="swe-km-row">
          <label class="swe-km-f"><span>{{ t('Ед. изм.') }}</span><input v-model="kUnit" type="text" :placeholder="t('%, т, чел…')" /></label>
          <label class="swe-km-f"><span>{{ t('Направление') }}</span>
            <select v-model="kDir"><option value="up">{{ t('больше — лучше') }}</option><option value="down">{{ t('меньше — лучше') }}</option></select>
          </label>
        </div>
        <div class="swe-km-row">
          <label class="swe-km-f"><span>{{ t('План') }}{{ year ? ' · ' + year : '' }}</span><input v-model="kPlan" type="number" step="any" placeholder="—" /></label>
          <label class="swe-km-f"><span>{{ t('Факт') }}{{ year ? ' · ' + year : '' }}</span><input v-model="kFact" type="number" step="any" placeholder="—" /></label>
        </div>
        <div class="swe-km-note">{{ t('Сохранится в модуле «KPI» под менеджером «ESG / Устойчивое развитие» — появится и в') }} <b>/kpi</b>.</div>
        <div class="swe-km-actions">
          <button class="swe-km-cancel" type="button" @click="closeKpi">{{ t('Отмена') }}</button>
          <button class="swe-km-save" type="button" :disabled="kSaving || !kName.trim()" @click="submitKpi">{{ kSaving ? t('Сохранение…') : t('Добавить KPI') }}</button>
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

/* Две панели «по типу KPI» (эталон KpiSummaryDashboard .kps-w / .kps-ind-row) */
.swe-grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media (max-width: 1100px) { .swe-grid2 { grid-template-columns: 1fr; } }
.swe-w {
  background: var(--card-bg, rgba(255, 255, 255, 0.82));
  backdrop-filter: blur(16px) saturate(1.5); -webkit-backdrop-filter: blur(16px) saturate(1.5);
  border: 1px solid var(--card-border, rgba(0,0,0,.05)); border-radius: 12px;
  padding: 14px 16px; display: flex; flex-direction: column;
}
.swe-w-t { font-size: 10.5px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; margin-bottom: 10px; }

.swe-obj-list { display: flex; flex-direction: column; gap: 10px; }
/* объект (портфель / компания) */
.swe-obj { display: flex; flex-direction: column; gap: 5px; animation: sweRowIn .4s var(--ease-standard, ease) var(--d, 0ms) both; }
.swe-obj.port .swe-obj-h { color: var(--p-deep, #5B53B8); font-weight: 700; }
.swe-obj-h { display: flex; align-items: center; gap: 7px; font-size: 11.5px; font-weight: 600; color: var(--t1, #1E2A4A); }
.swe-obj-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
@keyframes sweRowIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
/* секторный разделитель внутри панели */
.swe-obj-sec { display: flex; align-items: center; gap: 7px; margin-top: 4px; font-size: 9.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, #94A3B8); }
.swe-obj-sec-dot { width: 7px; height: 7px; border-radius: 2px; flex-shrink: 0; }
.swe-obj-sec-cnt { margin-left: 2px; font-size: 9px; font-weight: 700; color: var(--t3, #94A3B8); background: var(--bg2, #F6F5FB); border-radius: 999px; padding: 0 6px; }

.swe-items { display: flex; flex-direction: column; gap: 6px; padding-left: 15px; }
/* пункт-строка в стиле KPI-ряда (тонировка + верхняя полоса) */
.swe-item { position: relative; overflow: hidden; border-radius: 6px; padding: 8px 12px; display: flex; align-items: flex-start; gap: 8px; }
.swe-item.good { background: rgba(29, 158, 117, .05); }
.swe-item.bad  { background: rgba(226, 75, 74, .05); }
.swe-item.good::before, .swe-item.bad::before {
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
  border-top-left-radius: inherit; border-top-right-radius: inherit; pointer-events: none;
}
.swe-item.good::before { background: #1D9E75; }
.swe-item.bad::before  { background: #E24B4A; }
.swe-item-body { margin: 0; font-size: 11.5px; line-height: 1.5; color: var(--t2, #3a4256); flex: 1; }
.swe-item-body.ed { cursor: text; }
.swe-item-body.ed:hover { color: var(--t1, #1E2A4A); }
.swe-item.swe-item-new { flex-direction: column; align-items: stretch; }
.swe-empty { color: #CBD2E0; font-size: 12px; padding-left: 2px; }

.swe-ta { width: 100%; box-sizing: border-box; resize: vertical; min-height: 42px; padding: 7px 10px; border: 1.5px solid #7C6FF7; border-radius: 9px; font-family: inherit; font-size: 11.5px; line-height: 1.45; color: var(--t1, #1E2A4A); outline: none; }
.swe-confirm { display: inline-flex; gap: 4px; flex-shrink: 0; margin-top: 4px; }
.swe-ok, .swe-no { width: 22px; height: 22px; border-radius: 6px; border: none; cursor: pointer; font-size: 12px; font-weight: 700; display: inline-flex; align-items: center; justify-content: center; transition: background .12s, color .12s; }
.swe-ok { background: #DCFCE7; color: #1D9E75; }
.swe-ok:hover:not(:disabled) { background: #16A34A; color: #fff; }
.swe-ok:disabled { opacity: .5; cursor: default; }
.swe-no { background: #F1F5F9; color: #94A3B8; }
.swe-no:hover { background: #E2E8F0; color: #475569; }
.swe-add { align-self: flex-start; font-size: 10.5px; font-weight: 600; color: var(--p-deep, #5B53B8); background: rgba(124,111,247,.08); border: 1px dashed rgba(124,111,247,.4); border-radius: 8px; padding: 3px 10px; cursor: pointer; font-family: inherit; transition: background .14s, border-color .14s; }
.swe-add:hover { background: rgba(124,111,247,.15); border-color: #7C6FF7; }

/* ESG-KPI лента под панелями */
.swe-kpi-sec { margin-top: 12px; }
.swe-kpi-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 10px; }
.swe-kpi-co { background: var(--bg2, #FAFAFC); border: 1px solid var(--card-border, rgba(0,0,0,.05)); border-radius: 9px; padding: 10px 12px; display: flex; flex-direction: column; gap: 6px; }
.swe-kpi-co-h { display: flex; align-items: center; gap: 7px; font-size: 11px; font-weight: 600; color: var(--t1, #1E2A4A); }

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

@media (min-width: 2200px) {
  .swe-title { font-size: 21px; } .swe-item-body { font-size: 14px; } .swe-obj-h { font-size: 13.5px; }
  .swe-w-t { font-size: 12.5px; }
}

.swe-item-main { flex: 1; min-width: 0; }
.swe-item-main.ed { cursor: text; }
.swe-item-main.ed:hover .swe-item-body { color: var(--t1, #1E2A4A); }

/* ── Подпись автора: премиум-футер карточки вывода ──
   Аватар — единый пурпур-градиент платформы; имя — основной кегль,
   должность · компания — тихие; дата — справа, табличные цифры. */
.swe-author {
  display: flex; align-items: center; gap: 8px;
  margin-top: 8px; padding-top: 7px;
  border-top: 1px solid rgba(127, 119, 221, .14);
}
.swe-author-ava {
  width: 22px; height: 22px; border-radius: 50%; flex: none;
  display: inline-flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #8B83E8 0%, #534AB7 100%);
  color: #fff; font-size: 8.5px; font-weight: 600; letter-spacing: .03em;
  box-shadow: 0 1px 3px rgba(83, 74, 183, .30);
}
.swe-author-col { display: flex; flex-direction: column; min-width: 0; line-height: 1.25; }
.swe-author-name { font-size: 10.5px; font-weight: 600; color: var(--t1, #1E2A4A); }
.swe-author-sub {
  font-size: 9.5px; color: var(--t3, #94A3B8);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.swe-author-date {
  margin-left: auto; flex: none;
  font-size: 9.5px; color: var(--t3, #94A3B8);
  font-variant-numeric: tabular-nums;
}

/* Удаление вывода: тихая кнопка, проявляется при наведении на карточку */
.swe-del {
  flex: none; width: 24px; height: 24px; margin-left: 2px;
  border: none; border-radius: 6px; background: transparent;
  color: var(--t3, #94A3B8); cursor: pointer;
  display: inline-flex; align-items: center; justify-content: center;
  opacity: 0; transition: opacity .12s, background .12s, color .12s;
}
.swe-item:hover .swe-del { opacity: 1; }
.swe-del:hover { background: rgba(226, 75, 74, .10); color: #E24B4A; }
.swe-del:disabled { opacity: .4; cursor: default; }
</style>
