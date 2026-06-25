<script setup lang="ts">
/**
 * ESGMaturityProfileModal — профиль ESG-зрелости компании.
 * Radar по 6 измерениям (из heatmap.dim_stage) + разбивка по стадиям.
 * Блок «ESG-рейтинги» — единый источник правды (AgencyRating, is_esg):
 * читается из /companies/{code}/ratings, правится через RatingEditModal в родителе.
 */
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import ModalShell from "@/components/ModalShell.vue";
import { Chart } from "@/utils/chartjsRegister";
import type { ESGMaturityCompany } from "@/api/esg";
import { ratingsApi, type AgencyRatingBrief, type AgencyRatingHistoryItem } from "@/api/ratings";

const props = defineProps<{ company: ESGMaturityCompany | null; canEdit?: boolean }>();
const emit = defineEmits<{
  (e: "close"): void;
  (e: "edit-rating", p: { companyId: string; companyName: string; agency: string; existing: AgencyRatingBrief | null }): void;
}>();

// ─── ESG-рейтинги компании (единый источник) ──────────────────────
const ESG_AGENCIES = ["Sustainable Fitch", "S&P ESG", "CDP"];
const ratings = ref<AgencyRatingBrief[]>([]);
const ratingsLoading = ref(false);

async function loadRatings() {
  histOpen.value = null;
  if (!props.company) { ratings.value = []; return; }
  ratingsLoading.value = true;
  try {
    const data = await ratingsApi.getCompanyRatings(props.company.company_code);
    ratings.value = data.esg || [];
  } catch { ratings.value = []; }
  finally { ratingsLoading.value = false; }
}

// ─── История изменений рейтинга (динамика) ────────────────────────
const histOpen = ref<string | null>(null);          // agency раскрытой истории
const histItems = ref<AgencyRatingHistoryItem[]>([]);
const histLoading = ref(false);
const ACTION_LBL: Record<string, string> = { create: "создан", update: "изменён", delete: "удалён", snapshot: "снимок" };
async function toggleHistory(agency: string) {
  if (histOpen.value === agency) { histOpen.value = null; return; }
  histOpen.value = agency;
  histItems.value = [];
  if (!props.company) return;
  histLoading.value = true;
  try {
    const data = await ratingsApi.getRatingHistory(props.company.company_code, agency);
    histItems.value = data.items || [];
  } catch { histItems.value = []; }
  finally { histLoading.value = false; }
}
function histDate(iso: string): string {
  try { return new Date(iso).toLocaleDateString("ru", { day: "2-digit", month: "short", year: "numeric" }); }
  catch { return iso; }
}

const addableAgencies = computed(() =>
  ESG_AGENCIES.filter((a) => !ratings.value.some((r) => r.agency === a)),
);

function editRating(agency: string, existing: AgencyRatingBrief | null) {
  if (!props.canEdit || !props.company) return;
  emit("edit-rating", {
    companyId: props.company.company_id,
    companyName: props.company.company_name || props.company.company_code,
    agency, existing,
  });
}

const DIMS = [
  { key: "D1", label: "ISO-системы", max: 4, desc: "Системы менеджмента ISO 14001 / 45001 / 50001" },
  { key: "D2", label: "Отчётность", max: 4, desc: "ESG-отчётность: GRI/SASB → IFRS SDS → независимый assurance" },
  { key: "D3", label: "Рейтинги", max: 4, desc: "Независимые ESG-рейтинги агентств (Fitch / S&P / CDP)" },
  { key: "D4", label: "Климат", max: 4, desc: "Стратегия: выбросы Scope 1–2 → риски → декарбонизация → реализация" },
  { key: "D5", label: "Риски", max: 4, desc: "ESG-риски: double-materiality → оценка → интеграция в ERP" },
  { key: "D6", label: "KPI", max: 4, desc: "ESG-KPI устойчивого развития на уровне менеджмента" },
];

function emsColor(e: number): string { return e >= 70 ? "#1D9E75" : e >= 40 ? "#D97706" : "#E24B4A"; }
function stageOf(key: string): number { return props.company?.dim_stage?.[key] ?? 0; }

const canvas = ref<HTMLCanvasElement | null>(null);
let chart: Chart | null = null;

function render() {
  if (!canvas.value || !props.company) return;
  const data = DIMS.map((d) => Math.round((stageOf(d.key) / d.max) * 100));
  if (chart) { chart.destroy(); chart = null; }
  chart = new Chart(canvas.value, {
    type: "radar",
    data: {
      labels: DIMS.map((d) => d.label),
      datasets: [{
        data,
        backgroundColor: "rgba(124,111,247,.16)",
        borderColor: "#7C6FF7",
        borderWidth: 2,
        pointBackgroundColor: "#6C5CE7",
        pointBorderColor: "#fff",
        pointBorderWidth: 1.5,
        pointRadius: 4,
        pointHoverRadius: 6,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      animation: { duration: 700 },
      scales: {
        r: {
          min: 0, max: 100, beginAtZero: true,
          ticks: { display: false, stepSize: 25 },
          grid: { color: "#ECEAF5" },
          angleLines: { color: "#E7E5F2" },
          pointLabels: { font: { size: 11, weight: 600 }, color: "#475569" },
        },
      },
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c: { raw: unknown }) => `${c.raw}%` } } },
    },
  } as never);
}

watch(() => props.company, async (c) => {
  if (c) { loadRatings(); await nextTick(); render(); }
  else { ratings.value = []; }
}, { immediate: true });
onBeforeUnmount(() => { if (chart) chart.destroy(); });

const ems = computed(() => props.company?.ems ?? 0);
</script>

<template>
  <ModalShell :open="!!company" size="lg" @close="emit('close')">
    <template #header v-if="company">
      <div class="mp-head">
        <div>
          <div class="mp-eyebrow">{{ company.sector_name || company.company_code }} · ESG-зрелость</div>
          <div class="mp-title">{{ company.company_name || company.company_code }}</div>
        </div>
        <div class="mp-ems" :style="{ color: emsColor(ems) }">
          <span class="mp-ems-n">{{ Math.round(ems) }}</span><span class="mp-ems-u">EMS</span>
        </div>
      </div>
    </template>

    <div v-if="company" class="mp-body">
      <div class="mp-radar"><canvas ref="canvas"></canvas></div>
      <div class="mp-dims">
        <div v-for="d in DIMS" :key="d.key" class="mp-dim">
          <div class="mp-dim-top">
            <span class="mp-dim-l">{{ d.label }}</span>
            <span class="mp-dim-st" :class="'st'+stageOf(d.key)">стадия {{ stageOf(d.key) }} / {{ d.max }}</span>
          </div>
          <div class="mp-dim-bar"><i :style="{ width: (stageOf(d.key)/d.max*100)+'%' }"></i></div>
          <div class="mp-dim-desc">{{ d.desc }}</div>
        </div>
      </div>
    </div>

    <!-- ESG-рейтинги — единый источник правды (AgencyRating) -->
    <div v-if="company" class="mp-ratings">
      <div class="mp-r-head">
        <span class="mp-r-title">ESG-рейтинги <span class="mp-r-cnt">{{ ratings.length }}</span></span>
        <span class="mp-r-src">Единый источник · синхронизировано с разделом «Рейтинги» и рабочим столом компании</span>
      </div>

      <div v-if="ratingsLoading" class="mp-r-empty">Загрузка рейтингов…</div>
      <template v-else>
        <div v-if="ratings.length" class="mp-r-list">
          <div v-for="r in ratings" :key="r.id" class="mp-r-wrap">
            <div class="mp-r-item">
              <div class="mp-r-l">
                <span class="mp-r-ag">{{ r.agency }}</span>
                <span class="mp-r-val">{{ r.score || r.rating || '—' }}</span>
                <span v-if="r.outlook" class="mp-r-out">{{ r.outlook }}</span>
              </div>
              <div class="mp-r-r">
                <span v-if="r.rating_date_text" class="mp-r-date">{{ r.rating_date_text }}</span>
                <a v-if="r.report_url" class="mp-r-doc" :href="r.report_url" target="_blank" rel="noopener" title="Отчёт">отчёт</a>
                <button class="mp-r-hist" type="button" :class="{ on: histOpen === r.agency }"
                        @click="toggleHistory(r.agency)" title="История изменений">история</button>
                <button v-if="canEdit" class="mp-r-edit" type="button" @click="editRating(r.agency, r)">Изменить</button>
              </div>
            </div>
            <Transition name="mp-hist">
              <div v-if="histOpen === r.agency" class="mp-hist">
                <div v-if="histLoading" class="mp-hist-empty">Загрузка истории…</div>
                <template v-else>
                  <div v-if="histItems.length" class="mp-hist-tl">
                    <div v-for="(h, i) in histItems" :key="h.id" class="mp-hist-row" :style="{ '--d': (i*40)+'ms' }">
                      <span class="mp-hist-dot" :class="'a-'+h.action"></span>
                      <span class="mp-hist-val">{{ h.score || h.rating || '—' }}</span>
                      <span v-if="h.outlook" class="mp-hist-out">{{ h.outlook }}</span>
                      <span class="mp-hist-act" :class="'a-'+h.action">{{ ACTION_LBL[h.action] || h.action }}</span>
                      <span class="mp-hist-when">{{ histDate(h.created_at) }}</span>
                      <span v-if="h.changed_by_name" class="mp-hist-who">· {{ h.changed_by_name }}</span>
                    </div>
                  </div>
                  <div v-else class="mp-hist-empty">История пуста — изменения появятся здесь после правок</div>
                </template>
              </div>
            </Transition>
          </div>
        </div>
        <div v-else class="mp-r-empty">Независимых ESG-рейтингов пока нет</div>

        <div v-if="canEdit && addableAgencies.length" class="mp-r-add">
          <button v-for="a in addableAgencies" :key="a" class="mp-r-add-btn" type="button" @click="editRating(a, null)">
            + {{ a }}
          </button>
        </div>
      </template>
    </div>
  </ModalShell>
</template>

<style scoped>
.mp-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; width: 100%; }
.mp-eyebrow { font-size: 10px; font-weight: 500; letter-spacing: .08em; text-transform: uppercase; color: var(--t3, #94A3B8); }
.mp-title { font-size: 18px; font-weight: 500; color: var(--t1, #1E2A4A); margin-top: 3px; }
.mp-ems { display: inline-flex; align-items: baseline; gap: 5px; }
.mp-ems-n { font-size: 30px; font-weight: 700; font-feature-settings: 'tnum'; }
.mp-ems-u { font-size: 11px; font-weight: 600; color: var(--t3, #94A3B8); }

.mp-body { display: grid; grid-template-columns: 320px 1fr; gap: 22px; }
.mp-radar { height: 300px; position: relative; }
.mp-dims { display: flex; flex-direction: column; gap: 12px; }
.mp-dim { }
.mp-dim-top { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
.mp-dim-l { font-size: 12.5px; font-weight: 600; color: var(--t1, #1E2A4A); }
.mp-dim-st { font-size: 10.5px; font-weight: 600; padding: 1px 7px; border-radius: 5px; }
.mp-dim-st.st0 { background: #F1F5F9; color: #94A3B8; }
.mp-dim-st.st1 { background: #FEF9C3; color: #D97706; }
.mp-dim-st.st2 { background: #E0F2FE; color: #378ADD; }
.mp-dim-st.st3 { background: #EDE9FE; color: #6C5CE7; }
.mp-dim-st.st4 { background: #DCFCE7; color: #1D9E75; }
.mp-dim-bar { height: 5px; border-radius: 3px; background: #ECEAF5; overflow: hidden; margin: 5px 0 4px; }
.mp-dim-bar i { display: block; height: 100%; border-radius: 3px; background: linear-gradient(90deg, #8B7FF0, #6C5CE7); transition: width .5s var(--ease-standard, ease); }
.mp-dim-desc { font-size: 10.5px; color: var(--t3, #94A3B8); line-height: 1.35; }

/* ─── ESG-рейтинги (единый источник) ─── */
.mp-ratings { margin-top: 20px; padding-top: 18px; border-top: 1px solid var(--border, #ECEAF5); }
.mp-r-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.mp-r-title { font-size: 13px; font-weight: 600; color: var(--t1, #1E2A4A); display: inline-flex; align-items: center; gap: 7px; }
.mp-r-cnt { font-size: 11px; font-weight: 600; color: var(--brand, #6C5CE7); background: color-mix(in srgb, var(--brand, #6C5CE7) 10%, #fff); border-radius: 20px; padding: 1px 8px; }
.mp-r-src { font-size: 10.5px; color: var(--t3, #94A3B8); }
.mp-r-list { display: flex; flex-direction: column; gap: 8px; }
.mp-r-item { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 9px 13px; border-radius: 10px; background: var(--surface-2, #FAFAFC); border: 1px solid var(--border, #ECEAF5); }
.mp-r-l { display: inline-flex; align-items: baseline; gap: 10px; min-width: 0; }
.mp-r-ag { font-size: 12.5px; font-weight: 600; color: var(--t1, #1E2A4A); }
.mp-r-val { font-size: 12.5px; font-weight: 600; color: var(--brand, #6C5CE7); font-feature-settings: 'tnum'; }
.mp-r-out { font-size: 11px; color: var(--t2, #475569); }
.mp-r-r { display: inline-flex; align-items: center; gap: 12px; flex-shrink: 0; }
.mp-r-date { font-size: 10.5px; color: var(--t3, #94A3B8); font-feature-settings: 'tnum'; }
.mp-r-doc { font-size: 10.5px; color: var(--brand, #6C5CE7); text-decoration: none; }
.mp-r-doc:hover { text-decoration: underline; }
.mp-r-edit { font-size: 11px; font-weight: 600; color: var(--brand, #6C5CE7); background: color-mix(in srgb, var(--brand, #6C5CE7) 8%, #fff); border: none; border-radius: 7px; padding: 4px 11px; cursor: pointer; transition: background .15s ease; }
.mp-r-edit:hover { background: color-mix(in srgb, var(--brand, #6C5CE7) 15%, #fff); }
.mp-r-empty { font-size: 11.5px; color: var(--t3, #94A3B8); padding: 6px 0; }

/* История рейтинга (динамика) */
.mp-r-wrap { display: flex; flex-direction: column; }
.mp-r-hist { font-size: 10.5px; font-weight: 600; color: var(--t3, #94A3B8); background: transparent; border: 1px solid var(--border, #ECEAF5); border-radius: 7px; padding: 3px 9px; cursor: pointer; transition: all .15s ease; }
.mp-r-hist:hover, .mp-r-hist.on { color: var(--brand, #6C5CE7); border-color: color-mix(in srgb, var(--brand, #6C5CE7) 40%, #fff); background: color-mix(in srgb, var(--brand, #6C5CE7) 6%, #fff); }
.mp-hist { overflow: hidden; padding: 4px 13px 8px; }
.mp-hist-empty { font-size: 11px; color: var(--t3, #94A3B8); padding: 6px 2px; }
.mp-hist-tl { display: flex; flex-direction: column; gap: 0; border-left: 2px solid var(--border, #ECEAF5); margin-left: 4px; padding-left: 12px; }
.mp-hist-row { position: relative; display: flex; align-items: baseline; gap: 7px; padding: 5px 0; font-size: 11.5px; animation: mpHistIn .35s ease var(--d, 0ms) both; }
@keyframes mpHistIn { from { opacity: 0; transform: translateX(-4px); } to { opacity: 1; transform: translateX(0); } }
.mp-hist-dot { position: absolute; left: -19px; top: 9px; width: 9px; height: 9px; border-radius: 50%; background: #94A3B8; box-shadow: 0 0 0 3px #fff; }
.mp-hist-dot.a-create { background: #1D9E75; }
.mp-hist-dot.a-update { background: #6C5CE7; }
.mp-hist-dot.a-delete { background: #E24B4A; }
.mp-hist-val { font-weight: 600; color: var(--t1, #1E2A4A); font-feature-settings: 'tnum'; }
.mp-hist-out { font-size: 10.5px; color: var(--t2, #475569); }
.mp-hist-act { font-size: 9.5px; font-weight: 600; border-radius: 5px; padding: 1px 6px; background: #F1F5F9; color: #64748B; }
.mp-hist-act.a-create { background: #DCFCE7; color: #1D9E75; }
.mp-hist-act.a-update { background: #EDE9FE; color: #6C5CE7; }
.mp-hist-act.a-delete { background: #FEE2E2; color: #E24B4A; }
.mp-hist-when { font-size: 10.5px; color: var(--t3, #94A3B8); font-feature-settings: 'tnum'; }
.mp-hist-who { font-size: 10.5px; color: var(--t3, #94A3B8); }
.mp-hist-enter-active, .mp-hist-leave-active { transition: max-height .28s ease, opacity .2s ease; max-height: 400px; }
.mp-hist-enter-from, .mp-hist-leave-to { max-height: 0; opacity: 0; }
.mp-r-add { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.mp-r-add-btn { font-size: 11px; font-weight: 600; color: var(--t2, #475569); background: #fff; border: 1px dashed var(--border-strong, #D9D7E8); border-radius: 8px; padding: 5px 11px; cursor: pointer; transition: border-color .15s ease, color .15s ease; }
.mp-r-add-btn:hover { border-color: var(--brand, #6C5CE7); color: var(--brand, #6C5CE7); }

@media (max-width: 720px) { .mp-body { grid-template-columns: 1fr; } .mp-radar { height: 260px; } }
@media (min-width: 2200px) {
  .mp-title { font-size: 24px; } .mp-ems-n { font-size: 40px; }
  .mp-body { grid-template-columns: 420px 1fr; gap: 30px; } .mp-radar { height: 380px; }
  .mp-dim-l { font-size: 15px; } .mp-dim-desc { font-size: 13px; }
  .mp-r-title { font-size: 16px; } .mp-r-ag, .mp-r-val { font-size: 15px; }
  .mp-r-item { padding: 12px 18px; } .mp-r-edit { font-size: 13px; padding: 6px 15px; }
}
</style>
