<script setup lang="ts">
/**
 * SoeHealthDrillModal — детали SOE Health Check по компании: каждый
 * коэффициент со значением, зоной и порог-шкалой (5 сегментов, маркер
 * позиции), блоки «Тянут вниз» / «Сильные стороны» (стиль KPI good/bad).
 */
import { computed, ref, watch } from "vue";
import ModalShell from "@/components/ModalShell.vue";
import Odometer from "@/components/Odometer.vue";
import { api } from "@/api/client";
import type { SoeCompany, SoeRatio } from "@/components/Financials/SoeHealthBoard.vue";

const props = defineProps<{
  open: boolean;
  company: SoeCompany | null;
  zones: { key: string; label: string; color: string }[];
  year: number;
  standard: string;
}>();
const emit = defineEmits<{ (e: "close"): void }>();

// ─── Финансовая выписка (ОФР + Баланс) — ленивая подгрузка ───────────
interface StmtRow { code: string; label: string; total: boolean;
  cur: number | null; prev: number | null; var_pct: number | null }
interface Statement { year: number; prev_year: number; standard: string;
  income_statement: StmtRow[]; balance_sheet: StmtRow[]; has_data: boolean }
const stmt = ref<Statement | null>(null);
const stmtLoading = ref(false);
const stmtError = ref<string | null>(null);
let stmtSeq = 0;

async function loadStatement() {
  const c = props.company;
  if (!props.open || !c) return;
  const my = ++stmtSeq;
  stmtLoading.value = true; stmtError.value = null; stmt.value = null;
  try {
    const r = await api.get<Statement>(`/financials/soe-health/company/${c.code}`, {
      params: { year: props.year, standard: props.standard },
    });
    if (my !== stmtSeq) return;
    stmt.value = r.data;
  } catch (e: unknown) {
    if (my !== stmtSeq) return;
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    stmtError.value = err?.response?.data?.detail || err?.message || "Не удалось загрузить";
  } finally {
    if (my === stmtSeq) stmtLoading.value = false;
  }
}
watch(() => [props.open, props.company?.code, props.year, props.standard], loadStatement, { immediate: true });

function fmtMoney(v: number | null): string {
  if (v == null) return "—";
  if (Math.abs(v) >= 1000) return (v / 1000).toLocaleString("ru", { maximumFractionDigits: 1 }) + " трлн";
  return v.toLocaleString("ru", { maximumFractionDigits: 0 }) + " млрд";
}
function varColor(v: number | null): string {
  if (v == null) return "#9AA0AE";
  if (v > 0) return "#1D9E75";
  if (v < 0) return "#E24B4A";
  return "#9AA0AE";
}
function fmtVar(v: number | null): string {
  if (v == null) return "—";
  return (v > 0 ? "+" : "") + v.toFixed(1) + "%";
}

function zoneColor(band: number | null): string {
  if (band == null) return "#94A3B8";
  return props.zones[Math.min(band, 5) - 1]?.color || "#94A3B8";
}
function zoneLabel(band: number | null): string {
  if (band == null) return "н/д";
  return props.zones[Math.min(band, 5) - 1]?.label || "н/д";
}
function fmtVal(r: SoeRatio): string {
  if (r.value == null) return r.note || "нет данных";
  if (r.fmt === "pct") return (r.value * 100).toFixed(1) + "%";
  if (r.fmt === "days") return Math.round(r.value) + " дн";
  return r.value.toFixed(2) + "×";
}
function fmtThrVal(r: SoeRatio, t: number): string {
  return r.fmt === "pct" ? Math.round(t * 100) + "%" : String(t);
}
// позиция маркера на шкале: центр сегмента бенда (5 сегментов по 20%)
function markerPos(r: SoeRatio): number | null {
  if (r.band == null) return null;
  return (r.band - 1) * 20 + 10;
}

const rows = computed(() => props.company?.ratios || []);
const worst = computed(() =>
  rows.value.filter((r) => r.band != null && r.band >= 4)
    .sort((a, b) => (b.band || 0) - (a.band || 0)).slice(0, 3));
const best = computed(() =>
  rows.value.filter((r) => r.band != null && r.band <= 2)
    .sort((a, b) => (a.band || 9) - (b.band || 9)).slice(0, 3));
</script>

<template>
  <ModalShell :open="open && !!company" size="lg" @close="emit('close')">
    <template v-if="company" #header>
      <div class="shd-head">
        <div class="shd-head-l">
          <div class="shd-eyebrow">SOE Health Check Tool · {{ standard }} · FY {{ year }}</div>
          <h2 class="shd-title">
            <span class="shd-dot" :style="{ background: company.sector_color || '#94A3B8' }" />
            {{ company.name || company.code }}
          </h2>
          <div class="shd-meta">{{ company.sector_name || '—' }} · оценено коэффициентов: {{ company.available }} из {{ company.ratios.length }}</div>
        </div>
        <div class="shd-badges">
          <div v-if="company.z_score" class="shd-zbadge" :title="'Altman Z-Score (модель развив. рынков). ' + company.z_score.zone.label"
               :style="{ borderColor: company.z_score.zone.color + '55', color: company.z_score.zone.color }">
            <div class="shd-zbadge-k">Z-Score</div>
            <div class="shd-zbadge-v">{{ company.z_score.z.toFixed(2) }}</div>
            <div class="shd-zbadge-l">{{ company.z_score.zone.label }}</div>
          </div>
          <div v-if="company.overall != null" class="shd-score" :style="{ background: company.zone?.color || '#94A3B8' }">
            <div class="shd-score-v"><Odometer :value="company.overall.toFixed(1)" /></div>
            <div class="shd-score-l">{{ company.zone?.label }}</div>
          </div>
        </div>
      </div>
    </template>

    <div v-if="company" class="shd-body">
      <!-- Сильные/слабые — стиль KPI-панелей good/bad -->
      <div v-if="worst.length || best.length" class="shd-grid2">
        <div class="shd-w">
          <div class="shd-w-t" style="color:#E24B4A">↓ Тянут вниз</div>
          <div v-for="r in worst" :key="r.key" class="shd-ind bad">
            <span class="shd-ind-name">{{ r.label }}</span>
            <b :style="{ color: zoneColor(r.band) }">{{ fmtVal(r) }}</b>
          </div>
          <div v-if="!worst.length" class="shd-none">нет критичных зон</div>
        </div>
        <div class="shd-w">
          <div class="shd-w-t" style="color:#1D9E75">↑ Сильные стороны</div>
          <div v-for="r in best" :key="r.key" class="shd-ind good">
            <span class="shd-ind-name">{{ r.label }}</span>
            <b :style="{ color: zoneColor(r.band) }">{{ fmtVal(r) }}</b>
          </div>
          <div v-if="!best.length" class="shd-none">—</div>
        </div>
      </div>

      <!-- Все коэффициенты с порог-шкалами -->
      <div class="shd-list">
        <div v-for="(r, i) in rows" :key="r.key" class="shd-row" :style="{ '--d': (i * 40) + 'ms' }">
          <div class="shd-row-top">
            <span class="shd-r-label" :title="r.formula">{{ r.label }}</span>
            <span class="shd-r-group">{{ r.group }}</span>
            <span class="shd-r-val" :style="{ color: zoneColor(r.band) }">{{ fmtVal(r) }}</span>
            <span class="shd-r-zone" :style="{ color: zoneColor(r.band), background: zoneColor(r.band) + '18' }">{{ zoneLabel(r.band) }}</span>
          </div>
          <div class="shd-scale">
            <div v-for="(z, zi) in zones" :key="z.key" class="shd-seg" :style="{ background: z.color }"
                 :title="z.label + (zi < 4 ? ' · порог ' + fmtThrVal(r, r.thresholds[zi]) : '')" />
            <div v-if="markerPos(r) != null" class="shd-marker" :style="{ left: markerPos(r) + '%' }" />
          </div>
          <div class="shd-thr">
            <span v-for="(t, ti) in r.thresholds" :key="ti" :style="{ left: ((ti + 1) * 20) + '%' }">{{ fmtThrVal(r, t) }}</span>
          </div>
        </div>
      </div>

      <!-- Финансовая выписка: ОФР + Баланс с Var(%) -->
      <div class="shd-stmt">
        <div v-if="stmtLoading" class="shd-stmt-state">Загрузка выписки…</div>
        <div v-else-if="stmtError" class="shd-stmt-state shd-stmt-err">{{ stmtError }}</div>
        <template v-else-if="stmt && stmt.has_data">
          <div class="shd-stmt-grid">
            <div v-if="stmt.income_statement.length" class="shd-stmt-col">
              <div class="shd-stmt-t">Отчёт о фин. результатах <span>млрд сум</span></div>
              <div class="shd-stmt-head">
                <span></span>
                <span>FY {{ stmt.year }}</span>
                <span>FY {{ stmt.prev_year }}</span>
                <span>Var</span>
              </div>
              <div v-for="row in stmt.income_statement" :key="row.code"
                   class="shd-stmt-row" :class="{ tot: row.total }">
                <span class="shd-stmt-lbl">{{ row.label }}</span>
                <span class="shd-stmt-v">{{ fmtMoney(row.cur) }}</span>
                <span class="shd-stmt-v prev">{{ fmtMoney(row.prev) }}</span>
                <span class="shd-stmt-var" :style="{ color: varColor(row.var_pct) }">{{ fmtVar(row.var_pct) }}</span>
              </div>
            </div>
            <div v-if="stmt.balance_sheet.length" class="shd-stmt-col">
              <div class="shd-stmt-t">Баланс <span>млрд сум</span></div>
              <div class="shd-stmt-head">
                <span></span>
                <span>FY {{ stmt.year }}</span>
                <span>FY {{ stmt.prev_year }}</span>
                <span>Var</span>
              </div>
              <div v-for="row in stmt.balance_sheet" :key="row.code"
                   class="shd-stmt-row" :class="{ tot: row.total }">
                <span class="shd-stmt-lbl">{{ row.label }}</span>
                <span class="shd-stmt-v">{{ fmtMoney(row.cur) }}</span>
                <span class="shd-stmt-v prev">{{ fmtMoney(row.prev) }}</span>
                <span class="shd-stmt-var" :style="{ color: varColor(row.var_pct) }">{{ fmtVar(row.var_pct) }}</span>
              </div>
            </div>
          </div>
        </template>
        <div v-else-if="stmt" class="shd-stmt-state">Выписка за FY {{ year }} ({{ standard }}) недоступна</div>
      </div>
    </div>

    <template #footer>
      <span class="shd-note">RAG-оценка финансовой устойчивости · пороги настраиваемые · ниже балл = устойчивее</span>
      <button class="shd-ok" type="button" @click="emit('close')">Закрыть</button>
    </template>
  </ModalShell>
</template>

<style scoped>
.shd-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; width: 100%; }
.shd-eyebrow { font-size: 9.5px; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; color: var(--t3, #94A3B8); }
.shd-title { font-size: 17px; font-weight: 600; margin: 4px 0 0; color: var(--t1, #1E2A4A); display: flex; align-items: center; gap: 8px; }
.shd-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.shd-meta { font-size: 11px; color: var(--t3, #94A3B8); margin-top: 4px; }
.shd-badges { display: flex; align-items: stretch; gap: 8px; flex-shrink: 0; }
.shd-zbadge {
  border: 1.5px solid; border-radius: 13px; padding: 8px 14px; text-align: center;
  display: flex; flex-direction: column; justify-content: center; background: #fff;
  animation: shdPop .45s var(--ease-standard, ease) both;
}
.shd-zbadge-k { font-size: 8.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; opacity: .8; }
.shd-zbadge-v { font-size: 22px; font-weight: 600; line-height: 1.05; font-variant-numeric: tabular-nums; }
.shd-zbadge-l { font-size: 8.5px; font-weight: 600; opacity: .85; margin-top: 1px; }
.shd-score {
  border-radius: 13px; color: #fff; padding: 9px 16px; text-align: center; flex-shrink: 0;
  box-shadow: 0 6px 18px rgba(15,23,60,.18); animation: shdPop .45s var(--ease-standard, ease) both;
}
@keyframes shdPop { from { opacity: 0; transform: scale(.9); } to { opacity: 1; transform: scale(1); } }
.shd-score-v { font-size: 24px; font-weight: 600; line-height: 1; font-variant-numeric: tabular-nums; }
.shd-score-l { font-size: 9.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; margin-top: 3px; opacity: .92; }

.shd-body { display: flex; flex-direction: column; gap: 16px; }
.shd-grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
@media (max-width: 700px) { .shd-grid2 { grid-template-columns: 1fr; } }
.shd-w { background: var(--bg2, #FAFAFD); border-radius: 11px; padding: 11px 13px; }
.shd-w-t { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; margin-bottom: 7px; }
.shd-ind { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; padding: 6px 10px; border-radius: 7px; margin-bottom: 4px; position: relative; overflow: hidden; }
.shd-ind::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px; }
.shd-ind.bad { background: rgba(226,75,74,.05); }
.shd-ind.bad::before { background: #E24B4A; }
.shd-ind.good { background: rgba(29,158,117,.05); }
.shd-ind.good::before { background: #1D9E75; }
.shd-ind-name { font-size: 11.5px; color: var(--t1, #1E2A4A); font-weight: 500; }
.shd-ind b { font-size: 12px; font-variant-numeric: tabular-nums; }
.shd-none { font-size: 11px; color: #C4C8D4; font-style: italic; }

.shd-list { display: flex; flex-direction: column; gap: 13px; }
.shd-row { animation: shdRowIn .4s var(--ease-standard, ease) var(--d, 0ms) both; }
@keyframes shdRowIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
.shd-row-top { display: flex; align-items: baseline; gap: 9px; margin-bottom: 5px; }
.shd-r-label { font-size: 12px; font-weight: 600; color: var(--t1, #1E2A4A); cursor: help; border-bottom: 1px dashed rgba(148,163,184,.5); }
.shd-r-group { font-size: 9px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, #94A3B8); }
.shd-r-val { margin-left: auto; font-size: 13px; font-weight: 700; font-variant-numeric: tabular-nums; }
.shd-r-zone { font-size: 9.5px; font-weight: 700; border-radius: 6px; padding: 2px 7px; }
.shd-scale { position: relative; display: flex; gap: 2px; height: 8px; }
.shd-seg { flex: 1; border-radius: 3px; opacity: .32; transition: opacity .15s; }
.shd-row:hover .shd-seg { opacity: .5; }
.shd-marker {
  position: absolute; top: -3px; width: 3px; height: 14px; border-radius: 2px;
  background: var(--t1, #1E2A4A); box-shadow: 0 0 0 2.5px #fff, 0 1px 4px rgba(15,23,60,.35);
  transform: translateX(-50%); transition: left .5s var(--ease-standard, ease);
}
.shd-thr { position: relative; height: 12px; margin-top: 3px; }
.shd-thr span {
  position: absolute; transform: translateX(-50%);
  font-size: 8.5px; color: var(--t3, #94A3B8); font-variant-numeric: tabular-nums; white-space: nowrap;
}

/* Финансовая выписка */
.shd-stmt { border-top: 0.5px solid rgba(0,0,0,.08); padding-top: 14px; }
.shd-stmt-state { padding: 16px; text-align: center; font-size: 12px; color: var(--t3, #94A3B8); }
.shd-stmt-err { color: #E24B4A; }
.shd-stmt-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
@media (max-width: 760px) { .shd-stmt-grid { grid-template-columns: 1fr; } }
.shd-stmt-t { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em;
  color: var(--p-deep, #534AB7); margin-bottom: 8px; display: flex; justify-content: space-between; align-items: baseline; }
.shd-stmt-t span { font-size: 9px; font-weight: 500; color: var(--t3, #94A3B8); text-transform: none; letter-spacing: 0; }
.shd-stmt-head, .shd-stmt-row { display: grid; grid-template-columns: 1fr 74px 74px 56px; align-items: center; gap: 6px; }
.shd-stmt-head { padding: 0 0 5px; border-bottom: 0.5px solid rgba(0,0,0,.06); margin-bottom: 3px; }
.shd-stmt-head span { font-size: 9px; font-weight: 600; text-transform: uppercase; letter-spacing: .03em;
  color: var(--t3, #94A3B8); text-align: right; }
.shd-stmt-head span:first-child { text-align: left; }
.shd-stmt-row { padding: 4px 0; font-size: 11.5px; animation: shdRowIn .35s var(--ease-standard, ease) both; }
.shd-stmt-row.tot { font-weight: 700; border-top: 0.5px dashed rgba(0,0,0,.1); margin-top: 1px; }
.shd-stmt-row.tot .shd-stmt-lbl { color: var(--t1, #1E2A4A); }
.shd-stmt-lbl { color: var(--t2, #4B5468); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.shd-stmt-v { text-align: right; font-variant-numeric: tabular-nums; color: var(--t1, #1E2A4A); }
.shd-stmt-v.prev { color: var(--t3, #94A3B8); }
.shd-stmt-var { text-align: right; font-weight: 700; font-size: 10.5px; font-variant-numeric: tabular-nums; }

.shd-note { margin-right: auto; font-size: 10.5px; color: var(--t3, #94A3B8); font-style: italic; }
.shd-ok {
  font-size: 12.5px; font-weight: 600; font-family: inherit; color: #fff;
  background: linear-gradient(135deg, #8B7FFF 0%, #6C5CE7 100%);
  border: none; border-radius: 10px; padding: 9px 20px; cursor: pointer;
  box-shadow: 0 3px 12px rgba(108,92,231,.34); transition: transform .14s, box-shadow .14s;
}
.shd-ok:hover { transform: translateY(-1px); box-shadow: 0 6px 18px rgba(108,92,231,.45); }
</style>
