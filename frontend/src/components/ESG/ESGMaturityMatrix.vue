<script setup lang="ts">
/**
 * ESGMaturityMatrix — операционное ядро ESG Maturity Cockpit.
 * Строки = компании (по секторам), колонки = 6 измерений зрелости.
 * ISO/Отчётность/Климат/Риски редактируются inline (клик по чипу/степперу).
 * Рейтинги (D3) — клик открывает профиль (правка через единый источник AgencyRating). EMS — вычисляемый.
 */
import { computed, ref, watch } from "vue";
import { useToast } from "@/composables/useToast";
import { esgApi, type ESGMaturityHeatmap, type ESGMaturityCompany } from "@/api/esg";

const props = defineProps<{
  heatmap: ESGMaturityHeatmap | null;
  canEdit: boolean;
  search?: string;
}>();
const emit = defineEmits<{ (e: "saved"): void; (e: "open-company", id: string): void }>();

const toast = useToast();
const rows = ref<ESGMaturityCompany[]>([]);
watch(() => props.heatmap, (h) => { rows.value = h ? h.companies.map((c) => ({ ...c, cells: [...c.cells] })) : []; }, { immediate: true });

const filtered = computed(() => {
  const q = (props.search || "").trim().toLowerCase();
  const list = q
    ? rows.value.filter((c) => (c.company_name || c.company_code).toLowerCase().includes(q))
    : rows.value;
  return list;
});
// группировка по секторам с сохранением порядка
const grouped = computed(() => {
  const out: { key: string; name: string; color: string; companies: ESGMaturityCompany[] }[] = [];
  const idx = new Map<string, number>();
  for (const c of filtered.value) {
    const key = c.sector_code || "—";
    let i = idx.get(key);
    if (i === undefined) {
      i = out.length;
      idx.set(key, i);
      out.push({ key, name: c.sector_name || "Прочее", color: c.sector_color || "#94A3B8", companies: [] });
    }
    out[i].companies.push(c);
  }
  return out;
});

// ── helpers ───────────────────────────────────────────────────────────
function cellStage(c: ESGMaturityCompany, dim: string, sub = ""): number {
  const cell = c.cells.find((x) => x.dimension === dim && (x.sub_key || "") === sub);
  if (cell) return cell.stage || 0;
  return c.dim_stage?.[dim] ?? 0;
}
function emsColor(e: number): string {
  if (e >= 70) return "#1D9E75";
  if (e >= 40) return "#D97706";
  return "#E24B4A";
}
const ISO = [
  { sub: "iso14001", label: "14001", tip: "ISO 14001 · Экологический менеджмент" },
  { sub: "iso45001", label: "45001", tip: "ISO 45001 · Охрана труда и пром. безопасность" },
  { sub: "iso50001", label: "50001", tip: "ISO 50001 · Энергоменеджмент" },
];
const REP_LABELS = ["нет", "разовый", "регулярный", "IFRS SDS", "+ assurance"];
const REP_COLORS = ["#94A3B8", "#378ADD", "#378ADD", "#7C6FF7", "#1D9E75"];

// Короткое имя агентства для компактной ячейки рейтинга.
function agencyAbbr(a: string): string {
  const s = (a || "").toLowerCase();
  if (s.includes("fitch")) return "Fitch";
  if (s.includes("s&p") || s.includes("standard & poor") || s.includes("sp ")) return "S&P";
  if (s.includes("cdp")) return "CDP";
  if (s.includes("msci")) return "MSCI";
  if (s.includes("moody")) return "Moody’s";
  if (s.includes("sustainalytics")) return "Sustainalytics";
  if (s.includes("iss")) return "ISS";
  return a.length > 12 ? a.slice(0, 11) + "…" : a;
}

// ── inline-edit с подтверждением у ячейки (защита от случайной правки) ──
const saving = ref<string | null>(null);   // ключ редактируемой ячейки
function ckey(cid: string, dim: string, sub: string) { return `${cid}:${dim}:${sub}`; }

// Ожидающее подтверждения изменение (одна ячейка за раз). Клик НЕ применяет
// значение сразу — только формирует превью; применяется по ✓.
const pending = ref<{ c: ESGMaturityCompany; dim: string; sub: string; stage: number } | null>(null);
function isPending(c: ESGMaturityCompany, dim: string, sub = ""): boolean {
  const p = pending.value;
  return !!p && p.c.company_id === c.company_id && p.dim === dim && p.sub === sub;
}
// Стадия с учётом ожидающего изменения (превью в ячейке).
function dStage(c: ESGMaturityCompany, dim: string, sub = ""): number {
  return isPending(c, dim, sub) ? pending.value!.stage : cellStage(c, dim, sub);
}
function setPending(c: ESGMaturityCompany, dim: string, sub: string, stage: number) {
  if (!props.canEdit || saving.value) return;
  pending.value = { c, dim, sub, stage };
}
function cancelPending() { pending.value = null; }
async function confirmPending() {
  const p = pending.value;
  if (!p) return;
  pending.value = null;
  await setStage(p.c, p.dim, p.sub, p.stage);
}

async function setStage(c: ESGMaturityCompany, dim: string, sub: string, stage: number) {
  if (!props.canEdit || saving.value) return;
  const key = ckey(c.company_id, dim, sub);
  const cell = c.cells.find((x) => x.dimension === dim && (x.sub_key || "") === sub);
  const prev = cell ? cell.stage : null;
  // optimistic
  if (cell) cell.stage = stage;
  else c.cells.push({ dimension: dim, sub_key: sub, stage } as never);
  saving.value = key;
  try {
    const r = await esgApi.upsertMaturityCell({ company_id: c.company_id, year: props.heatmap!.year, dimension: dim, sub_key: sub, stage });
    if ((r as { queued?: boolean }).queued) toast.info("Отправлено на согласование");
    else { toast.success("Сохранено"); emit("saved"); }
  } catch (e: unknown) {
    if (cell) cell.stage = prev ?? 0;
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    toast.error("Не сохранено: " + (err?.response?.data?.detail || err?.message || "ошибка"));
  } finally { saving.value = null; }
}
// ISO chip: клик циклит превью 0→1→2→0 (применяется по ✓)
function cycleIso(c: ESGMaturityCompany, sub: string) {
  const s = dStage(c, "D1", sub);
  setPending(c, "D1", sub, s >= 2 ? 0 : s + 1);
}
// степпер: клик по сегменту i → превью стадии i+1 (повторный клик по вершине → −1)
function clickStep(c: ESGMaturityCompany, dim: string, i: number) {
  const cur = dStage(c, dim, "");
  setPending(c, dim, "", cur === i + 1 ? i : i + 1);
}
function cycleRep(c: ESGMaturityCompany) {
  const s = dStage(c, "D2", "");
  setPending(c, "D2", "", s >= 4 ? 0 : s + 1);
}
</script>

<template>
  <div class="mm-wrap">
    <table class="mm">
      <thead>
        <tr>
          <th class="mm-h-co">Компания</th>
          <th class="mm-h-grp" colspan="3">ISO-системы</th>
          <th class="mm-h">Отчётность</th>
          <th class="mm-h">Рейтинг</th>
          <th class="mm-h">Климат</th>
          <th class="mm-h">Риски</th>
          <th class="mm-h mm-h-ems">EMS</th>
        </tr>
        <tr class="mm-subh">
          <th class="mm-h-co"></th>
          <th v-for="x in ISO" :key="x.sub" :title="x.tip">{{ x.label }}</th>
          <th></th><th></th>
          <th title="Scope 1–2 → риски → план декарбонизации → реализация">●●●● 4 этапа</th>
          <th title="Double-materiality → кол. оценка → интеграция в ERM">●●● 3 этапа</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <template v-for="g in grouped" :key="g.key">
          <tr class="mm-sec"><td :colspan="9"><span class="mm-sec-dot" :style="{ background: g.color }"></span>{{ g.name }} · {{ g.companies.length }}</td></tr>
          <tr v-for="c in g.companies" :key="c.company_id" class="mm-row">
            <td class="mm-co" @click="emit('open-company', c.company_id)">
              <span class="mm-co-dot" :style="{ background: c.sector_color || '#94A3B8' }"></span>
              <span class="mm-co-name" :title="c.company_name || c.company_code">{{ c.company_name || c.company_code }}</span>
              <span class="mm-co-bar"><i :style="{ width: c.ems + '%', background: emsColor(c.ems) }"></i></span>
            </td>
            <!-- ISO -->
            <td v-for="x in ISO" :key="x.sub" class="mm-c mm-cedit">
              <button type="button" class="mm-iso" :class="['s'+dStage(c,'D1',x.sub), { ed: canEdit, pend: isPending(c,'D1',x.sub) }]"
                      :disabled="!canEdit" :title="x.tip" @click="cycleIso(c, x.sub)">
                {{ dStage(c,'D1',x.sub) >= 2 ? '✓' : dStage(c,'D1',x.sub) === 1 ? '◐' : '—' }}
              </button>
              <div v-if="isPending(c,'D1',x.sub)" class="mm-confirm">
                <button type="button" class="mm-ok" title="Применить" @click.stop="confirmPending">✓</button>
                <button type="button" class="mm-no" title="Отмена" @click.stop="cancelPending">✕</button>
              </div>
            </td>
            <!-- Отчётность -->
            <td class="mm-c mm-cedit">
              <button type="button" class="mm-pill" :class="{ ed: canEdit, pend: isPending(c,'D2','') }"
                      :style="{ color: REP_COLORS[dStage(c,'D2','')], background: REP_COLORS[dStage(c,'D2','')] + '1E' }"
                      :disabled="!canEdit" :title="'Отчётность: '+REP_LABELS[dStage(c,'D2','')]" @click="cycleRep(c)">
                {{ REP_LABELS[dStage(c,'D2','')] }}
              </button>
              <div v-if="isPending(c,'D2','')" class="mm-confirm">
                <button type="button" class="mm-ok" title="Применить" @click.stop="confirmPending">✓</button>
                <button type="button" class="mm-no" title="Отмена" @click.stop="cancelPending">✕</button>
              </div>
            </td>
            <!-- Рейтинг → сам рейтинг + агентство + ссылка (клик по ячейке → профиль) -->
            <td class="mm-c mm-rate-c">
              <div class="mm-rates" @click="emit('open-company', c.company_id)"
                   title="Открыть профиль компании">
                <template v-if="c.ratings && c.ratings.length">
                  <span v-for="(r, i) in c.ratings" :key="i" class="mm-rchip">
                    <span class="mm-rchip-v">{{ r.score || r.rating || '—' }}</span>
                    <span class="mm-rchip-ag">{{ agencyAbbr(r.agency) }}</span>
                    <a v-if="r.report_url" class="mm-rchip-lnk" :href="r.report_url" target="_blank"
                       rel="noopener" title="Открыть отчёт агентства" @click.stop>↗</a>
                  </span>
                </template>
                <span v-else class="mm-rate none">нет рейтинга</span>
              </div>
            </td>
            <!-- Климат stepper 4 -->
            <td class="mm-c mm-cedit">
              <span class="mm-step">
                <i v-for="i in 4" :key="i" class="mm-dot clm" :class="{ on: dStage(c,'D4','') >= i, ed: canEdit, pend: isPending(c,'D4','') }" @click="clickStep(c,'D4',i-1)"></i>
              </span>
              <div v-if="isPending(c,'D4','')" class="mm-confirm">
                <button type="button" class="mm-ok" title="Применить" @click.stop="confirmPending">✓</button>
                <button type="button" class="mm-no" title="Отмена" @click.stop="cancelPending">✕</button>
              </div>
            </td>
            <!-- Риски stepper 3 -->
            <td class="mm-c mm-cedit">
              <span class="mm-step">
                <i v-for="i in 3" :key="i" class="mm-dot rsk" :class="{ on: dStage(c,'D5','') >= i, ed: canEdit, pend: isPending(c,'D5','') }" @click="clickStep(c,'D5',i-1)"></i>
              </span>
              <div v-if="isPending(c,'D5','')" class="mm-confirm">
                <button type="button" class="mm-ok" title="Применить" @click.stop="confirmPending">✓</button>
                <button type="button" class="mm-no" title="Отмена" @click.stop="cancelPending">✕</button>
              </div>
            </td>
            <!-- EMS -->
            <td class="mm-c mm-ems"><span :style="{ color: emsColor(c.ems) }">{{ Math.round(c.ems) }}</span></td>
          </tr>
        </template>
        <tr v-if="!filtered.length"><td :colspan="9" class="mm-empty">Нет компаний</td></tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.mm-wrap { overflow: auto; border: 1px solid rgba(0,0,0,.06); border-radius: 12px; background: var(--bg1, #fff); max-height: calc(100vh - 320px); }
.mm { border-collapse: separate; border-spacing: 0; width: 100%; font-size: 12px; }
.mm thead th { position: sticky; top: 0; z-index: 4; background: #F6F5FB; color: var(--p-deep, #534AB7); font-weight: 700; font-size: 10px; text-transform: uppercase; letter-spacing: .04em; padding: 7px 8px; text-align: center; border-bottom: 1px solid #E7E5F2; }
/* Двухрядная шапка: первая строка top:0, вторая (под-заголовки) ниже на высоту первой.
   Селектор специфичнее `.mm thead th`, иначе top перебивался на 0 и строки слипались. */
.mm thead tr.mm-subh th { top: 29px; z-index: 3; font-size: 8.5px; font-weight: 600; color: #8a90a8; text-transform: none; letter-spacing: 0; padding: 3px 6px; }
.mm-h-grp { background: #EFEEF9 !important; }
.mm-h-co, td.mm-co { position: sticky; left: 0; z-index: 2; background: var(--bg1, #fff); text-align: left; min-width: 210px; max-width: 240px; }
.mm thead .mm-h-co { z-index: 4; background: #F6F5FB; }
.mm-h-ems { min-width: 46px; }

.mm-sec td { background: linear-gradient(90deg, rgba(127,119,221,.06), transparent); font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: var(--p-deep, #5B53B8); padding: 5px 10px; position: sticky; left: 0; }
.mm-sec-dot { display: inline-block; width: 7px; height: 7px; border-radius: 2px; margin-right: 7px; vertical-align: middle; }

.mm-row { transition: background .12s; }
.mm-row:hover td { background: rgba(127,119,221,.045); }
.mm-row:hover td.mm-co { background: #FBFAFF; }
.mm td { border-bottom: 1px solid #F1F0F7; padding: 5px 6px; vertical-align: middle; text-align: center; }
.mm-co { display: flex; align-items: center; gap: 7px; padding: 6px 10px !important; cursor: pointer; }
.mm-co-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.mm-co-name { flex: 1; min-width: 0; text-align: left; font-size: 11.5px; font-weight: 500; color: var(--t1, #1E2A4A); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.mm-co:hover .mm-co-name { color: var(--p-deep, #5B53B8); }
.mm-co-bar { width: 38px; height: 4px; border-radius: 3px; background: #ECEAF5; overflow: hidden; flex-shrink: 0; }
.mm-co-bar i { display: block; height: 100%; border-radius: 3px; transition: width .5s var(--ease-standard, ease); }

.mm-iso { width: 30px; height: 24px; border-radius: 6px; border: none; font-size: 12px; font-weight: 700; font-family: inherit; cursor: default; transition: transform .12s, box-shadow .12s; }
.mm-iso.s2 { background: #DCFCE7; color: #1D9E75; }
.mm-iso.s1 { background: #FEF9C3; color: #D97706; }
.mm-iso.s0 { background: #F1F5F9; color: #94A3B8; }
.mm-iso.ed { cursor: pointer; }
.mm-iso.ed:hover { transform: scale(1.08); box-shadow: 0 0 0 1px rgba(0,0,0,.08); }

.mm-pill { padding: 3px 9px; border-radius: 6px; border: none; font-size: 10.5px; font-weight: 600; font-family: inherit; cursor: default; white-space: nowrap; transition: transform .12s; }
.mm-pill.ed { cursor: pointer; }
.mm-pill.ed:hover { transform: scale(1.04); }

.mm-rate { font-size: 10.5px; font-weight: 600; color: var(--t2, #475569); }
.mm-rate.none { color: #C4C8D4; }
/* Ячейка рейтинга: сами значения + агентство + ссылка (клик по ячейке → профиль) */
.mm-rate-c { min-width: 96px; }
.mm-rates { display: inline-flex; flex-direction: column; gap: 3px; align-items: center; cursor: pointer; padding: 2px 6px; border-radius: 7px; transition: background .15s ease; }
.mm-rates:hover { background: color-mix(in srgb, var(--brand, #6C5CE7) 7%, #fff); }
.mm-rchip { display: inline-flex; align-items: baseline; gap: 4px; line-height: 1.15; white-space: nowrap; }
.mm-rchip-v { font-size: 11px; font-weight: 700; color: var(--p-deep, #534AB7); font-feature-settings: 'tnum'; }
.mm-rchip-ag { font-size: 9px; font-weight: 600; color: var(--t3, #94A3B8); text-transform: uppercase; letter-spacing: .02em; }
.mm-rchip-lnk { font-size: 10px; font-weight: 700; color: var(--brand, #6C5CE7); text-decoration: none; padding: 0 1px; border-radius: 4px; }
.mm-rchip-lnk:hover { background: color-mix(in srgb, var(--brand, #6C5CE7) 16%, #fff); }

.mm-step { display: inline-flex; gap: 4px; align-items: center; }
.mm-dot { width: 11px; height: 11px; border-radius: 50%; background: #E6E4F0; transition: transform .12s, background .15s; }
.mm-dot.clm.on { background: #1D9E75; }
.mm-dot.rsk.on { background: #6C5CE7; }
.mm-dot.ed { cursor: pointer; }
.mm-dot.ed:hover { transform: scale(1.25); }

/* Inline-подтверждение правки (защита от случайной правки) */
.mm-cedit { position: relative; }
.mm-iso.pend, .mm-pill.pend { outline: 2px dashed #7C6FF7; outline-offset: 1px; }
.mm-dot.pend { box-shadow: 0 0 0 2px rgba(124, 111, 247, .45); }
.mm-confirm { display: flex; justify-content: center; gap: 4px; margin-top: 5px; animation: mmConfIn .14s ease; }
@keyframes mmConfIn { from { opacity: 0; transform: translateY(-3px); } to { opacity: 1; transform: translateY(0); } }
.mm-ok, .mm-no { width: 22px; height: 20px; border-radius: 6px; border: none; cursor: pointer; font-size: 12px; font-weight: 700; line-height: 1; display: inline-flex; align-items: center; justify-content: center; transition: background .12s, color .12s; }
.mm-ok { background: #DCFCE7; color: #1D9E75; }
.mm-ok:hover { background: #16A34A; color: #fff; }
.mm-no { background: #F1F5F9; color: #94A3B8; }
.mm-no:hover { background: #E2E8F0; color: #475569; }

.mm-ems span { font-size: 13px; font-weight: 700; font-feature-settings: 'tnum'; }
.mm-empty { padding: 28px; text-align: center; color: var(--t3, #94A3B8); font-size: 12px; }

/* ─── Адаптив: от <14" ноутбуков до 60–75" стен-дисплеев ─── */
/* Компактные/малые экраны — матрица скроллится по горизонтали, sticky сохраняется */
@media (max-width: 1366px) {
  .mm-h-co, td.mm-co { min-width: 180px; max-width: 200px; }
}
@media (max-width: 1024px) {
  .mm { font-size: 11px; }
  .mm-h-co, td.mm-co { min-width: 160px; max-width: 180px; }
  .mm-iso { width: 26px; height: 22px; }
  .mm-wrap { max-height: calc(100vh - 280px); }
}
/* Большие дисплеи (4K, 60–75") — крупнее, читаемо с дистанции */
@media (min-width: 2200px) {
  .mm { font-size: 15px; }
  .mm thead th { font-size: 12px; padding: 10px 12px; }
  .mm-subh th { font-size: 11px; top: 40px; }
  .mm-h-co, td.mm-co { min-width: 300px; max-width: 360px; }
  .mm-co-name { font-size: 14.5px; }
  .mm-co-bar { width: 56px; height: 6px; }
  .mm-iso { width: 40px; height: 32px; font-size: 16px; }
  .mm-pill { font-size: 13px; padding: 5px 13px; }
  .mm-rate { font-size: 13px; }
  .mm-dot { width: 15px; height: 15px; }
  .mm-ems span { font-size: 18px; }
  .mm-wrap { max-height: calc(100vh - 360px); }
}
@media (min-width: 3400px) {
  .mm { font-size: 19px; }
  .mm thead th { font-size: 15px; }
  .mm-subh th { font-size: 13px; top: 50px; }
  .mm-h-co, td.mm-co { min-width: 400px; max-width: 480px; }
  .mm-co-name { font-size: 18px; }
  .mm-co-bar { width: 76px; height: 8px; }
  .mm-iso { width: 52px; height: 42px; font-size: 21px; border-radius: 9px; }
  .mm-pill { font-size: 16px; padding: 7px 17px; }
  .mm-rate { font-size: 16px; }
  .mm-dot { width: 20px; height: 20px; }
  .mm-ems span { font-size: 24px; }
}
</style>
